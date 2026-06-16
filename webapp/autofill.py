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

import os
import re

from . import ats

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


COVER_RE = re.compile(r"cover\s*letter", re.I)
RESUME_RE = re.compile(r"resume|résumé|\bcv\b", re.I)

# Voluntary self-identification fields, and the "decline" answer phrasing that
# varies wildly between ATSs ("Decline to self-identify" vs "I don't wish to
# answer" vs "Prefer not to say") — matched by intent, not exact text.
DEMOGRAPHIC_FIELDS = {"gender", "race_ethnicity", "veteran_status", "disability_status"}
DECLINE_RE = re.compile(
    r"decline|prefer\s*not|don'?t\s*wish|do\s*not\s*wish|not\s*to\s*(answer|say|disclose)"
    r"|do\s*not\s*want|won'?t\s*answer", re.I)

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
    # Voluntary self-identification (EEO). transgender is excluded from gender so
    # "do you identify as transgender?" isn't answered with the gender value.
    (r"(?<!trans)gender|gender\s*identity", "gender"),
    (r"\brace\b|racial|ethnic|hispanic|latin[ao]?", "race_ethnicity"),
    (r"veteran|military\s*service", "veteran_status"),
    (r"disab", "disability_status"),
    # Education.
    (r"school|university|college|institution|alma\s*mater", "school"),
    (r"\bdegree\b|qualification", "degree"),
    (r"discipline|field\s*of\s*study|\bmajor\b|concentration", "discipline"),
    (r"grad.{0,12}year|year\s*of\s*grad|completion\s*year", "graduation_year"),
    # Address.
    (r"street|address\s*line|mailing\s*address", "street_address"),
    (r"\bzip\b|postal\s*code|post\s*code", "postal_code"),
    (r"\bcountry\b", "country"),
    (r"\bcity\b", "city"),
    (r"\bstate\b|province", "state"),
    (r"how\s*did\s*you\s*hear|hear\s*about|referral\s*source", "_how_heard"),
    (r"location", "location"),
    (r"full[\s_-]*name|legal\s*name|your\s*name|\bname\b", "full_name"),
]]

# Fields we knowingly have no data for — skip with a clear reason instead of
# falling through to "no match".
NO_DATA_RULES: list[tuple[re.Pattern, str]] = [(re.compile(p, re.I), why) for p, why in [
    (r"\bgpa\b|grade\s*point", "no GPA in profile"),
    (r"sexual\s*orientation|transgender", "self-identification — left for you"),
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

# Identity/contact fields must NOT be typed into a combobox — a combobox that
# matched one of these is almost always a mislabelled neighbour (e.g. the
# country selector inside a phone field). Everything else (geography, education,
# demographics) is a legitimate dropdown target.
COMBO_TEXT_BLOCK = {
    "first_name", "last_name", "full_name", "email", "phone", "linkedin",
    "github", "portfolio", "current_company", "current_title",
    "salary_expectation", "years_experience",
}


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

        if field.get("value"):
            actions.append(_skip(field, "already filled"))
            continue

        if COVER_RE.search(desc):
            cover = values.get("cover_letter", "")
            if kind == "file":
                actions.append(_skip(field, "cover letter file — upload your own"))
            elif cover:
                actions.append(_action(field, "fill", cover, "cover_letter"))
            else:
                actions.append(_skip(field, "cover letter — add one to your profile"))
            continue

        if kind == "file":
            if RESUME_RE.search(desc) and resume_path:
                actions.append(_action(field, "upload", resume_path, "resume"))
            else:
                actions.append(_skip(field, "file upload — no matching document"))
            continue

        # "Choice" = anything we answer by picking a value: native <select>, a
        # custom React combobox, or a control the ATS schema tells us is a
        # dropdown even though it renders as a plain input. combo == needs the
        # open→click interaction (the executor reads live options) rather than
        # a native select_option.
        choice = kind in ("select", "combobox") or field.get("schema_select")
        combo = bool(choice and kind != "select")

        # Yes/no screening questions (choice / radio / checkbox).
        yesno_done = False
        if choice or kind in ("radio", "checkbox"):
            for pattern, rule_field in YESNO_RULES:
                if not pattern.search(desc):
                    continue
                answer = _yesno_answer(rule_field, values)
                if not answer:
                    actions.append(_skip(field, "no confident answer in profile"))
                elif choice:
                    opt = _pick_option(field.get("options", []), answer)
                    if opt:
                        actions.append(_action(field, "select", opt["text"], rule_field,
                                               opt_value=opt.get("value", ""), combo=combo))
                    elif combo:  # options render only once the menu is opened
                        actions.append(_action(field, "select", answer, rule_field, combo=True))
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
            if not no_data and not desc.strip():
                continue  # anonymous control (e.g. a React widget's hidden input)
            actions.append(_skip(field, no_data or "no matching profile field"))
            continue

        value = values.get(matched_field, "")
        if not value:
            actions.append(_skip(field, f"profile field '{matched_field}' is empty"))
            continue
        if matched_field in URL_FIELDS and (kind == "url" or "url" in desc):
            value = format_url(value)

        if choice:
            heard = matched_field == "_how_heard"
            decline = matched_field in DEMOGRAPHIC_FIELDS and bool(DECLINE_RE.search(value))
            options = field.get("options", [])
            if heard:
                opt = next((o for o in options if HOW_HEARD_OPTION.search(o.get("text", ""))), None)
            elif decline:  # match the decline option whatever its exact wording
                opt = next((o for o in options if DECLINE_RE.search(o.get("text", ""))), None)
            else:
                opt = _pick_option(options, value)
            combo_ok = heard or decline or matched_field not in COMBO_TEXT_BLOCK
            if opt:
                actions.append(_action(field, "select", opt["text"], matched_field,
                                       opt_value=opt.get("value", ""), combo=combo))
            elif combo and combo_ok:
                # menu not open yet — executor matches/typeaheads live options
                actions.append(_action(field, "select", "" if (heard or decline) else value,
                                       matched_field, combo=True, how_heard=heard, decline=decline))
            elif combo:
                # a combobox that matched a free-text field (e.g. phone country
                # selector) — don't risk typing into it.
                actions.append(_skip(field, "dropdown — pick it yourself"))
            else:
                actions.append(_skip(field, f"no option matching '{value[:40]}'"))
        else:
            actions.append(_action(field, "fill", value, matched_field))
    return actions


# --------------------------------------------------------- browser-side layer
# One pass over every control in a frame: tag with data-af, return descriptors.
_COLLECT_JS = """(fi) => {
  const out = [];
  // Clear handles from any previous pass — they persist on the elements, and a
  // stale one would make the dedupe guard skip the control on every re-fill.
  document.querySelectorAll('[data-af]').forEach(e => e.removeAttribute('data-af'));
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
  const SKIP = ['hidden', 'submit', 'button', 'image', 'reset'];
  // Native form controls plus ARIA comboboxes — Greenhouse's job-boards UI,
  // Ashby and Workday render dropdowns as custom widgets, not <select>.
  const nodes = new Set();
  document.querySelectorAll(
    'input, select, textarea, [role="combobox"], [aria-haspopup="listbox"]'
  ).forEach(e => nodes.add(e));
  let n = 0;
  nodes.forEach(el => {
    const tag = el.tagName.toLowerCase();
    const type = (el.type || tag).toLowerCase();
    if (SKIP.includes(type)) return;
    const role = (el.getAttribute('role') || '').toLowerCase();
    const haspopup = (el.getAttribute('aria-haspopup') || '').toLowerCase();
    let kind = type.startsWith('select') ? 'select'
             : (tag === 'input' || tag === 'textarea') ? type : '';
    if (kind !== 'select' &&
        (role === 'combobox' || haspopup === 'listbox' || el.getAttribute('aria-autocomplete')))
      kind = 'combobox';
    if (!kind) return;  // a non-field element that slipped through the selector
    // A combobox *wrapper* around the real control: keep the inner one only.
    if (kind === 'combobox' && tag !== 'input' && tag !== 'textarea'
        && el.querySelector('input, textarea, select')) return;
    if (!visible(el) && type !== 'file') return;  // file inputs hide behind styled buttons
    if (el.hasAttribute('data-af')) return;        // already collected this pass
    const label = (labelFor(el) || '').trim().slice(0, 300);
    const question = (questionFor(el) || '').trim().slice(0, 300);
    if (kind === 'combobox' && !label && !question) return;  // unlabeled menu, not a field
    const af = 'f' + fi + '-' + n++;
    el.setAttribute('data-af', af);
    const d = {
      af: af, kind: kind,
      name: el.getAttribute('name') || '', id: el.id || '',
      placeholder: el.getAttribute('placeholder') || '',
      autocomplete: el.getAttribute('autocomplete') || '',
      label: label, question: '', options: [], value: '', checked: false,
      required: el.getAttribute('aria-required') === 'true' || el.required === true,
    };
    if (d.kind === 'select') {
      d.options = Array.from(el.options || [])
        .map(o => ({value: o.value, text: (o.innerText || '').trim()})).slice(0, 200);
      if (el.selectedIndex > 0)
        d.value = (el.options[el.selectedIndex].innerText || '').trim();
    } else if (d.kind === 'radio' || d.kind === 'checkbox') {
      d.checked = el.checked;
      d.question = question;
    } else if (d.kind === 'combobox') {
      d.question = question;
      // A custom widget's chosen value lives in a sibling, not el.value — read
      // it so a re-pass over a still-hydrating form doesn't re-open it.
      let cur = (el.value || '').trim();
      if (!cur) {
        const ctrl = el.closest('[class*="control"], [class*="select"], [role="combobox"]')
                     || el.parentElement;
        const sv = ctrl && ctrl.querySelector(
          '[class*="singleValue"], [class*="single-value"], [class*="multiValue"]');
        if (sv) cur = (sv.innerText || '').trim();
      }
      d.value = cur;
    } else if (d.kind !== 'file') {
      d.value = el.value || '';
    }
    out.push(d);
  });
  return out;
}"""

FILLABLE_KINDS = {"text", "email", "tel", "url", "number", "textarea", "file",
                  "search", "combobox"}

# Where rendered dropdown options live after a custom widget is opened.
OPTION_SELECTOR = ('[role="option"], li[role="option"], .select__option, '
                   '[data-automation-id="promptOption"]')


def _enrich_with_schema(fields: list[dict], schema: dict) -> None:
    """Fold a Greenhouse ``?questions=true`` schema into the collected DOM
    descriptors: exact option labels, required flags, and — crucially — the
    knowledge that a plainly-rendered input is really a dropdown
    (``schema_select``), so plan() answers it instead of skipping it."""
    for field in fields:
        # New job-boards UI keys fields by id (id="question_64335515"); the
        # legacy UI uses name="job_application[...]". Try both.
        key = field.get("id", "")
        if key not in schema:
            key = ats.greenhouse_field_name(field.get("name", ""))
        spec = schema.get(key)
        if not spec:
            continue
        if spec.get("label") and not field.get("label"):
            field["label"] = spec["label"]
        if spec.get("required"):
            field["required"] = True
        if ats.is_greenhouse_select_type(spec.get("type", "")):
            if not field.get("options"):
                field["options"] = spec.get("options", [])
            if field.get("kind") != "select":
                field["schema_select"] = True


def _combo_select(frame, locator, action) -> bool:
    """Drive a custom dropdown / combobox: open it, read the rendered options,
    click the one matching the wanted value (or, for 'how did you hear', the
    first careers-page-ish option). Falls back to type-and-pick for typeaheads.
    Bounded by short timeouts; never raises."""
    try:
        locator.scroll_into_view_if_needed(timeout=1500)
        locator.click(timeout=2500)
    except Exception:  # noqa: BLE001
        return False
    option_loc = frame.locator(OPTION_SELECTOR)
    try:
        option_loc.first.wait_for(state="visible", timeout=2000)
    except Exception:  # noqa: BLE001 — typeahead shows options only after typing
        pass
    try:
        texts = option_loc.all_inner_texts()
    except Exception:  # noqa: BLE001
        texts = []
    options = [{"text": t.strip(), "value": ""} for t in texts if t and t.strip()]
    if action.get("how_heard"):
        target = next((o for o in options if HOW_HEARD_OPTION.search(o["text"])), None)
    elif action.get("decline"):
        target = next((o for o in options if DECLINE_RE.search(o["text"])), None)
    else:
        target = _pick_option(options, action.get("value", ""))
    if target:
        try:
            option_loc.filter(
                has_text=re.compile(re.escape(target["text"]), re.I)
            ).first.click(timeout=2000)
            return True
        except Exception:  # noqa: BLE001
            pass
    wanted = action.get("value", "")
    if wanted and not action.get("how_heard"):  # typeahead: type, then take a suggestion
        try:
            locator.fill(wanted, timeout=1500)
        except Exception:  # noqa: BLE001
            try:
                locator.type(wanted, delay=20)
            except Exception:  # noqa: BLE001
                return False
        try:
            option_loc.first.wait_for(state="visible", timeout=1500)
            option_loc.first.click(timeout=1500)
            return True
        except Exception:  # noqa: BLE001
            try:
                locator.press("Enter")
                return True
            except Exception:  # noqa: BLE001
                return False
    return False


def _stable_key(field: dict) -> str:
    """A handle that survives re-collection across SPA hydration passes (the
    data-af handle does not). Used to skip controls already handled."""
    return (field.get("id") or field.get("name") or field.get("label")
            or field.get("question") or "")


# Ops worth remembering across passes — re-doing a dropdown/checkbox/upload is
# disruptive, whereas text fills are naturally idempotent (already-filled skip).
_RECORD_OPS = {"select", "check", "upload"}


def merge_resume(profile: dict, resume_fields: dict | None) -> dict:
    """Layer resume-derived values UNDER the profile: a profile value wins, but
    an empty/missing one falls back to the resume. Lets a sparse profile still
    fill from the resume, without ever overriding what the user set."""
    if not resume_fields:
        return profile
    merged = dict(resume_fields)
    merged.update({k: v for k, v in profile.items() if v})
    return merged


def _set_resume_file(locator, path: str, name: str = "") -> None:
    """Attach the resume. When the user's original filename is known, upload the
    bytes under THAT name so the form shows it (not the on-disk 'resume.pdf')."""
    if name and name != os.path.basename(path):
        with open(path, "rb") as fh:
            buffer = fh.read()
        mime = "application/pdf" if name.lower().endswith(".pdf") else "application/octet-stream"
        locator.set_input_files({"name": name, "mimeType": mime, "buffer": buffer}, timeout=5000)
    else:
        locator.set_input_files(path, timeout=5000)


def run_fill(page, profile: dict, resume_path: str = "", schema: dict | None = None,
             done_keys: set | None = None, resume_fields: dict | None = None,
             resume_name: str = "") -> dict:
    """Collect controls from every frame, plan, and execute. Returns
    {filled, fillable, fields, skipped}; never raises on a per-field basis.
    ``schema`` (optional Greenhouse field map) sharpens dropdown handling.
    ``done_keys`` (optional, mutated in place) carries controls already handled
    on a previous pass so a re-fill of a hydrating form doesn't redo them.
    ``resume_fields`` (optional) backfills fields the profile leaves blank."""
    done_keys = done_keys if done_keys is not None else set()
    profile = merge_resume(profile, resume_fields)
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

    if schema:
        _enrich_with_schema(all_fields, schema)

    key_of = {f["af"]: _stable_key(f) for f in all_fields}
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
        key = key_of.get(action["af"], "")
        if key and key in done_keys:
            continue  # answered on an earlier pass — don't redo, don't renoise
        frame = frame_of.get(action["af"])
        if frame is None:
            continue
        locator = frame.locator(f'[data-af="{action["af"]}"]')
        try:
            if action["op"] == "fill":
                locator.fill(action["value"], timeout=2500)
            elif action["op"] == "select" and action.get("combo"):
                if not _combo_select(frame, locator, action):
                    result["skipped"].append(
                        {"field": action["field"], "note": "dropdown — pick it yourself"})
                    continue
            elif action["op"] == "select":
                try:
                    locator.select_option(label=action["value"], timeout=2500)
                except Exception:  # noqa: BLE001
                    locator.select_option(value=action.get("opt_value", ""), timeout=2500)
            elif action["op"] == "check":
                locator.check(timeout=2500)
            elif action["op"] == "upload":
                _set_resume_file(locator, action["value"], resume_name)
            result["filled"] += 1
            result["fields"].append(action["field"])
            if key and action["op"] in _RECORD_OPS:
                done_keys.add(key)
        except Exception:  # noqa: BLE001 — keep going field by field
            result["skipped"].append({"field": action["field"], "note": "could not fill"})
    return result


_APPLY_TEXT = re.compile(r"\b(apply|i'?m interested)\b", re.I)
_APPLY_NEG = re.compile(r"applied|application status|how to apply|apply filter", re.I)
_APPLY_LEAD = re.compile(r"^\s*apply\b", re.I)


def click_apply_button(page) -> bool:
    """On a posting page with no form, click the 'Apply' button/link to reach
    the application form. Handles <a>, <button> and role=button widgets and
    the common text variants ('Apply', 'Apply for this job', "I'm interested").
    Never used when fillable fields are present, never clicks submit controls."""
    for getter in (lambda: page.get_by_role("button", name=_APPLY_TEXT),
                   lambda: page.get_by_role("link", name=_APPLY_TEXT)):
        try:
            locator = getter()
            for i in range(min(locator.count(), 6)):
                el = locator.nth(i)
                try:
                    text = el.inner_text(timeout=500) or ""
                except Exception:  # noqa: BLE001
                    text = ""
                if _APPLY_NEG.search(text):
                    continue
                if (el.get_attribute("type") or "").lower() == "submit":
                    continue
                el.click(timeout=3000)
                return True
        except Exception:  # noqa: BLE001
            continue
    # Fallback: raw elements whose own text starts with "apply".
    for selector in ("a", "button", '[role="button"]'):
        try:
            locator = page.locator(selector).filter(has_text=_APPLY_LEAD).first
            if not locator.count():
                continue
            if (locator.get_attribute("type") or "").lower() == "submit":
                continue
            locator.click(timeout=3000)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False
