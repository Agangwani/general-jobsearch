"""SEC EDGAR Form D enrichment — pure selection/parsing plus an offline
end-to-end with a fake HTTP session (no network). XML/JSON shapes are taken
verbatim from live SEC responses."""

from jobsearch.funding_edgar import (
    _is_company_match,
    edgar_total_raised,
    parse_amount_sold,
    select_company_filings,
    total_raised_dollars,
)

# A real Form D primary_doc.xml, trimmed to the fields we read.
FORM_D_XML = """<?xml version="1.0"?>
<edgarSubmission>
  <primaryIssuer><entityName>Middesk, Inc.</entityName></primaryIssuer>
  <offeringData><offeringSalesAmounts>
    <totalOfferingAmount>16000000</totalOfferingAmount>
    <totalAmountSold>16000000</totalAmountSold>
    <totalRemaining>0</totalRemaining>
  </offeringSalesAmounts></offeringData>
</edgarSubmission>"""


def _hit(display_name, cik="0001928657", adsh="0001928657-22-000001",
         file_num="021-000001", file_date="2022-06-01"):
    return {"_id": f"{adsh}:primary_doc.xml", "_source": {
        "ciks": [cik], "display_names": [display_name],
        "adsh": adsh, "file_num": [file_num], "file_date": file_date}}


def test_is_company_match_rejects_spv_and_accepts_exact():
    # The SPV that actually shows up for a "Middesk" query — the investor's
    # vehicle, not the company. Its name doesn't normalize to "middesk".
    assert not _is_company_match("Gaingels Middesk LLC (CIK 0001928657)", "Middesk")
    # The company's own filing matches (Inc./legal suffix normalizes away).
    assert _is_company_match("Middesk, Inc. (CIK 0001928657)", "Middesk")
    # A distinctive SPV phrase that survives normalization is still rejected.
    assert not _is_company_match("Acme SPV, a series of XYZ", "Acme")


def test_is_company_match_accepts_holdco_and_ventures_names():
    # Regression: "holdings" is a legal suffix normalize_company_name strips, so
    # a company filing as "X Holdings" must NOT be rejected as an SPV. Same for
    # legitimate operating companies named "... Ventures".
    assert _is_company_match("Acme Holdings, Inc. (CIK 0001234567)", "Acme Holdings")
    assert _is_company_match("Acme Holdings LLC", "Acme")
    assert _is_company_match("Bright Ventures, Inc.", "Bright Ventures")


def test_parse_amount_sold():
    assert parse_amount_sold(FORM_D_XML) == 16_000_000
    assert parse_amount_sold("<edgarSubmission/>") is None


def test_select_company_filings_keeps_only_the_company_and_dedups_shape():
    hits = [
        _hit("Gaingels Middesk LLC (CIK 0001928657)"),          # SPV -> rejected
        _hit("Middesk, Inc. (CIK 0001928657)", file_num="021-A"),
    ]
    picked = select_company_filings(hits, "Middesk")
    assert len(picked) == 1
    assert picked[0]["cik"] == "0001928657"
    assert picked[0]["adsh"] == "0001928657-22-000001"


def test_total_raised_dollars_sums_distinct_offerings():
    assert total_raised_dollars({"021-A": 5_000_000, "021-B": 20_000_000}) == 25_000_000
    assert total_raised_dollars({}) == 0


class _FakeResp:
    def __init__(self, *, json_data=None, text=""):
        self._json = json_data
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        pass


def _xml_with_amount(dollars):
    return FORM_D_XML.replace("16000000", str(dollars))


class _FakeSession:
    """Routes efts search -> JSON hits, archive -> Form D XML (by accession when
    an xml_by_adsh map is given, else a single body). Records calls."""
    request_timeout = 30

    def __init__(self, hits, xml=FORM_D_XML, xml_by_adsh=None):
        self._hits, self._xml, self._by_adsh, self.calls = hits, xml, xml_by_adsh or {}, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(url)
        if "search-index" in url:
            return _FakeResp(json_data={"hits": {"hits": self._hits}})
        for adsh_nodash, xml in self._by_adsh.items():
            if adsh_nodash in url:
                return _FakeResp(text=xml)
        return _FakeResp(text=self._xml)


def test_edgar_total_raised_end_to_end_offline():
    session = _FakeSession(
        hits=[_hit("Gaingels Middesk LLC (CIK 0001928657)"),
              _hit("Middesk, Inc.", file_num="021-B")])
    assert edgar_total_raised(session, "Middesk") == {"total_raised": "$16M"}


def test_edgar_total_raised_blank_when_only_spv_matches():
    session = _FakeSession(hits=[_hit("Gaingels Middesk LLC (CIK 0001928657)")])
    assert edgar_total_raised(session, "Middesk") == {}


def test_edgar_sums_distinct_offerings_but_not_amendments():
    # Two DISTINCT offerings (different file_num) -> summed: $5M + $20M = $25M.
    session = _FakeSession(
        hits=[_hit("Acme, Inc.", adsh="0000000000-22-000001", file_num="021-A"),
              _hit("Acme, Inc.", adsh="0000000000-23-000002", file_num="021-B")],
        xml_by_adsh={"000000000022000001": _xml_with_amount(5_000_000),
                     "000000000023000002": _xml_with_amount(20_000_000)})
    assert edgar_total_raised(session, "Acme") == {"total_raised": "$25M"}

    # Regression: an original + its amendment for the SAME round, BOTH missing
    # file_num, must NOT be double-counted. Amendment restates the cumulative
    # $8M; the latest filing wins -> $8M, not $5M + $8M = $13M.
    session2 = _FakeSession(
        hits=[_hit("Acme, Inc.", adsh="0000000000-22-000001", file_num="", file_date="2022-01-01"),
              _hit("Acme, Inc.", adsh="0000000000-23-000002", file_num="", file_date="2023-01-01")],
        xml_by_adsh={"000000000022000001": _xml_with_amount(5_000_000),
                     "000000000023000002": _xml_with_amount(8_000_000)})
    assert edgar_total_raised(session2, "Acme") == {"total_raised": "$8M"}


def test_edgar_total_raised_degrades_to_empty_on_error():
    class _Boom:
        request_timeout = 30

        def get(self, *a, **k):
            raise RuntimeError("network down")

    assert edgar_total_raised(_Boom(), "Middesk") == {}
    assert edgar_total_raised(_FakeSession([], ""), "") == {}
