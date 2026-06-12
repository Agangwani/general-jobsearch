"""Auto-fill engine for the integrated apply browser.

Flow per tab (full diagram in docs/design-autofill.md): one JS pass collects
every visible form control on the page (all frames — Greenhouse embeds its
form in an iframe), tagging each with a data-af handle. plan() then matches
all of them against the profile in one go and decides, per control, whether
to fill / select / check / upload — or to skip it with a reason. Values are
formatted per field type (phone punctuation, salary with $ and thousands
separators, https:// on URL inputs), not dumped raw.

Hard rules:
- The engine NEVER clicks submit. click_apply_button() exists only to get
  from a posting page to its application form, and is never called when a
  form is already present.
- Already-filled controls are never overwritten.
- Demographic/EEO questions, cover letters, and anything without a confident
  profile answer are skipped and reported, so the user knows exactly what is
  left for their review pass.

plan() is pure logic over field-descriptor dicts → offline-testable.
run_fill() is the thin Playwright layer that collects descriptors and
executes the plan.
"""

from __future__ import annotations

import re

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


# ------------------------------------------------------------ value formatting
def split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.split()
    if not parts:
        return "", ""
    return parts[0], parts[-1] if len(parts) > 1 else ""


def parse_location(location: str) -> tuple[str, str]:
    """'New York, NY' → ('New York', 'New York'); state comes back full-name."""
    if "," not in location:
        return location.strip(), ""
    city, _, rest = location.partition(",")
    token = rest.strip().split()[0].strip(".").upper() if rest.strip() else ""
    return city.strip(), STATES.get(token, rest.strip())


def format_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone


def format_salary(salary: str) -> str:
    bare = salary.replace(",", "").replace("$", "").strip()
    if bare.isdigit():
        return f"${int(bare):,}"
    return salary


def format_url(value: str) -> str:
    if value and not value.lower().startswith(("http://", "https://")):
        return f"https://{value}"
    return value


def _yesno(value: str) -> str:
    """Map a free-text profile answer to 'Yes'/'No' — empty if unsure."""
    v = value.strip().lower()
    if not v:
        return ""
    if re.match(r"^(no\b|none|false|n$)", v):
        return "No"
    if re.match(r"^(yes\b|y$|true)", v) or re.search(
            r"citizen|authoriz|permanent|green\s*card", v):
        return "Yes"
    return ""


# ------------------------------------------------------------- matching rules
def _descriptor(field: dict) -> str:
    return " ".join(
        str(field.get(k) or "")
        for k in ("label", "question", "name", "id", "placeholder", "autocomplete")
    ).lower()


EEO_RE = re.compile(
    r"gender|race|ethnic|veteran|disab|sexual\s*orientation|transgender"
    r"|hispanic|latin[ox]?|demographic|identity\s*survey", re.I)
COVER_RE = re.compile(r"cover\s*letter", re.I)
RESUME_RE = re.compile(r"resume|résumé|\bcv\b", re.I)

# Pattern → profile field. Order matters: specific before generic ("first
# name" must win before the bare-"name" fallback at the bottom).
TEXT_RULES: list[tuple[re.Pattern, str]] = [(re.compile(p, re.I), f) for p, f in [
    (r"first[\s_-]*name|given[\s_-]*name", "first_name"),
    (r"last[\s_-]*name|family[\s_-]*name|surname", "last_name"),
    (r"e-?mail", "email"),
    (r"phone|mobile|\bcell\b", "phone"),
    (r"linked\s*in", "linkedin"),
    (r"git\s*hub", "github"),
    (r"portfolio|personal\s*(web\s*)?site|website|other\s*url|\burl\b", "portfolio"),
    (r"current\s*(company|employer)|\bemployer\b|company\s*name", "current_company"),
    (r"(current|job)[\s_-]*title|current\s*(role|position)", "current_title"),
    (r"years?.{0,16}experience|experience.{0,10}years?", "years_experience"),
    (r"salary|compensation|desired\s*pay|pay\s*expectation", "salary_expectation"),
    (r"notice\s*period|when\s*can\s*you\s*start|availab", "notice_period"),
    (r"pronoun", "preferred_pronouns"),
    (r"\bcity\b", "city"),
    (r"\bstate\b|province", "state"),
    (r"how\s*did\s*you\s*hear|hear\s*about|referral\s*source", "_how_heard"),
    (r"location", "location"),
    (r"full[\s_-]*name|legal\s*name|your\s*name|\bname\b", "full_name"),
]]

# Fields we knowingly have no data for — skip with a clear reason instead of
# falling through to "no match".
NO_DATA_RULES: list[tuple[re.Pattern, str]] = [(re.compile(p, re.I), why) for p, why in [
    (r"\bzip\b|postal", "no postal code in profile"),
    (r"street|address\s*line", "no street address in profile"),
    (r"school|university|degree|education|gpa", "education — left for you"),
]]

# Yes/no screening questions answered from the profile.
YESNO_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(authoriz|eligib|legal).{0,40}work|work\s*authorization", re.I),
     "work_authorization"),
    (re.compile(r"sponsor", re.I), "requires_sponsorship"),
    (re.compile(r"(at\s*least|over|minimum\s*of)\s*18|18\s*years", re.I), "_always_yes"),
]

URL_FIELDS = {"linkedin", "github", "portfolio"}
HOW_HEARD_TEXT = "Company careers page"
HOW_HEARD_OPTION = re.compile(r"compan|career|website|direct", re.I)


def _values(profile: dict) -> dict:
    first, last = split_name(profile.get("full_name", ""))
    city, state = parse_location(profile.get("location", ""))
    values = dict(profile)
    values.update({
        "first_name": first, "last_name": last, "city": city, "state": state,
        "phone": format_phone(profile.get("phone", "")),
        "salary_expectation": format_salary(profile.get("salary_expectation", "")),
        "_how_heard": HOW_HEARD_TEXT,
    })
    return values


def _pick_option(options: list[dict], wanted: str) -> dict | None:
    """exact match → startswith → contains, all case-insensitive."""
    w = wanted.strip().lower()
    if not w:
        return None
    for match in (
        lambda t: t == w,
        lambda t: t.startswith(w),
        lambda t: w in t or t in w and t,
    ):
        for opt in options:
            text = opt.get("text", "").strip().lower()
            if text and match(text):
                return opt
    return None


def _yesno_answer(rule_field: str, values: dict) -> str:
    if rule_field == "_always_yes":
        return "Yes"
    return _yesno(values.get(rule_field, ""))


def _skip(field: dict, why: str) -> dict:
    return {"af": field["af"], "op": "skip", "field": field.get("label") or field.get("name") or field["kind"],
            "value": "", "note": why}


def _action(field: dict, op: str, value: str, profile_field: str, **extra) -> dict:
    return {"af": field["af"], "op": op, "value": value, "field": profile_field, **extra}


def plan(fields: list[dict], profile: dict, resume_path: str = "") -> list[dict]:
    """Decide an action for every collected control. Returns a list of dicts:
    op ∈ fill | select | check | upload | skip."""
    values = _values(profile)
    actions: list[dict] = []
    for field in fields:
        kind = field.get("kind", "text")
        if kind in ("hidden", "password", "submit", "button", "image", "reset"):
            continue
        desc = _descriptor(field)

        if EEO_RE.search(desc):
            actions.append(_skip(field, "demographic question — left for your review"))
            continue
        if COVER_RE.search(desc):
            actions.append(_skip(field, "cover letter — write your own"))
            continue

        if kind == "file":
            if RESUME_RE.search(desc) and resume_path:
                actions.append(_action(field, "upload", resume_path, "resume"))
            else:
                actions.append(_skip(field, "file upload — no matching document"))
            continue

        if field.get("value"):
            actions.append(_skip(field, "already filled"))
            continue

        # Yes/no screening questions (select / radio / checkbox).
        yesno_done = False
        if kind in ("select", "radio", "checkbox"):
            for pattern, rule_field in YESNO_RULES:
                if not pattern.search(desc):
                    continue
                answer = _yesno_answer(rule_field, values)
                if not answer:
                    actions.append(_skip(field, "no confident answer in profile"))
                elif kind == "select":
                    opt = _pick_option(field.get("options", []), answer)
                    if opt:
                        actions.append(_action(field, "select", opt["text"],
                                               rule_field, opt_value=opt.get("value", "")))
                    else:
                        actions.append(_skip(field, f"wanted '{answer}' — no matching option"))
                elif kind == "radio":
                    label = (field.get("label") or "").strip().lower()
                    if label.startswith(answer.lower()):
                        actions.append(_action(field, "check", answer, rule_field))
                    # the non-matching radios of the group: no action, no noise
                elif kind == "checkbox":
                    if answer == "Yes" and not field.get("checked"):
                        actions.append(_action(field, "check", answer, rule_field))
                yesno_done = True
                break
        if yesno_done:
            continue
        if kind in ("radio", "checkbox"):
            continue  # unknown choice questions: silently left for the user

        # Typed fields by input type, before label heuristics.
        matched_field = ""
        if kind == "email":
            matched_field = "email"
        elif kind == "tel":
            matched_field = "phone"
        else:
            for pattern, profile_field in TEXT_RULES:
                if pattern.search(desc):
                    matched_field = profile_field
                    break

        if not matched_field:
            no_data = next((why for p, why in NO_DATA_RULES if p.search(desc)), "")
            actions.append(_skip(field, no_data or "no matching profile field"))
            continue

        value = values.get(matched_field, "")
        if not value:
            actions.append(_skip(field, f"profile field '{matched_field}' is empty"))
            continue
        if matched_field in URL_FIELDS and (kind == "url" or "url" in desc):
            value = format_url(value)

        if kind == "select":
            wanted = HOW_HEARD_OPTION if matched_field == "_how_heard" else None
            opt = (next((o for o in field.get("options", []) if wanted.search(o.get("text", ""))), None)
                   if wanted else _pick_option(field.get("options", []), value))
            if opt:
                actions.append(_action(field, "select", opt["text"], matched_field,
                                       opt_value=opt.get("value", "")))
            else:
                actions.append(_skip(field, f"no option matching '{value[:40]}'"))
        else:
            actions.append(_action(field, "fill", value, matched_field))
    return actions


# --------------------------------------------------------- browser-side layer
# One pass over every control in a frame: tag with data-af, return descriptors.
_COLLECT_JS = """(fi) => {
  const out = [];
  const visible = el => !!(el.offsetParent || el.getClientRects().length);
  const labelFor = el => {
    if (el.labels && el.labels.length)
      return Array.from(el.labels).map(l => l.innerText || '').join(' ');
    const aria = el.getAttribute('aria-label');
    if (aria) return aria;
    const ids = el.getAttribute('aria-labelledby');
    if (ids) {
      const t = ids.split(/\\s+/).map(i => {
        const n = document.getElementById(i); return n ? n.innerText : '';
      }).join(' ');
      if (t.trim()) return t;
    }
    const wrap = el.closest('label');
    return wrap ? wrap.innerText : '';
  };
  const questionFor = el => {
    const fs = el.closest('fieldset');
    if (fs) { const lg = fs.querySelector('legend'); if (lg) return lg.innerText; }
    const box = el.closest('[class*="field"],[class*="question"],[class*="form-group"],li');
    if (box) {
      const lab = box.querySelector('label,legend,[class*="label"]');
      if (lab && !lab.contains(el)) return lab.innerText;
    }
    return '';
  };
  let n = 0;
  document.querySelectorAll('input, select, textarea').forEach(el => {
    const type = (el.type || el.tagName).toLowerCase();
    if (['hidden', 'submit', 'button', 'image', 'reset'].includes(type)) return;
    if (!visible(el) && type !== 'file') return;  // file inputs hide behind styled buttons
    const af = 'f' + fi + '-' + n++;
    el.setAttribute('data-af', af);
    const d = {
      af: af,
      kind: type.startsWith('select') ? 'select' : type,
      name: el.name || '', id: el.id || '',
      placeholder: el.placeholder || '',
      autocomplete: el.getAttribute('autocomplete') || '',
      label: (labelFor(el) || '').trim().slice(0, 300),
      question: '', options: [], value: '', checked: false,
    };
    if (d.kind === 'select') {
      d.options = Array.from(el.options)
        .map(o => ({value: o.value, text: (o.innerText || '').trim()})).slice(0, 200);
      if (el.selectedIndex > 0)
        d.value = (el.options[el.selectedIndex].innerText || '').trim();
    } else if (d.kind === 'radio' || d.kind === 'checkbox') {
      d.checked = el.checked;
      d.question = (questionFor(el) || '').trim().slice(0, 300);
    } else if (d.kind !== 'file') {
      d.value = el.value || '';
    }
    out.push(d);
  });
  return out;
}"""

FILLABLE_KINDS = {"text", "email", "tel", "url", "number", "textarea", "file", "search"}


def run_fill(page, profile: dict, resume_path: str = "") -> dict:
    """Collect controls from every frame, plan, and execute. Returns
    {filled, fillable, fields, skipped}; never raises on a per-field basis."""
    all_fields: list[dict] = []
    frame_of: dict[str, object] = {}
    for fi, frame in enumerate(page.frames):
        try:
            collected = frame.evaluate(_COLLECT_JS, fi)
        except Exception:  # noqa: BLE001 — cross-origin or detached frames
            continue
        for field in collected:
            frame_of[field["af"]] = frame
        all_fields.extend(collected)

    result = {
        "filled": 0,
        "fillable": sum(1 for f in all_fields if f.get("kind") in FILLABLE_KINDS),
        "fields": [],
        "skipped": [],
    }
    for action in plan(all_fields, profile, resume_path):
        if action["op"] == "skip":
            result["skipped"].append({"field": action["field"], "note": action["note"]})
            continue
        frame = frame_of.get(action["af"])
        if frame is None:
            continue
        locator = frame.locator(f'[data-af="{action["af"]}"]')
        try:
            if action["op"] == "fill":
                locator.fill(action["value"], timeout=2500)
            elif action["op"] == "select":
                try:
                    locator.select_option(label=action["value"], timeout=2500)
                except Exception:  # noqa: BLE001
                    locator.select_option(value=action.get("opt_value", ""), timeout=2500)
            elif action["op"] == "check":
                locator.check(timeout=2500)
            elif action["op"] == "upload":
                locator.set_input_files(action["value"], timeout=5000)
            result["filled"] += 1
            result["fields"].append(action["field"])
        except Exception:  # noqa: BLE001 — keep going field by field
            result["skipped"].append({"field": action["field"], "note": "could not fill"})
    return result


_APPLY_TEXT = re.compile(r"^\s*apply\b", re.I)


def click_apply_button(page) -> bool:
    """On a posting page with no form, click the 'Apply' button/link to reach
    the application form. Never used when fillable fields are present, and
    never clicks submit-type controls."""
    for selector in ("a", "button"):
        try:
            locator = page.locator(selector).filter(has_text=_APPLY_TEXT).first
            if not locator.count():
                continue
            if (locator.get_attribute("type") or "").lower() == "submit":
                continue
            locator.click(timeout=3000)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False
