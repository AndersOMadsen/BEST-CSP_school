import streamlit as st
import pandas as pd
import requests
import io
import json
import re
import anthropic
from pathlib import Path

# Always resolve asset paths relative to this file, regardless of working directory
ASSETS = Path(__file__).parent / "assets"
CURATED = Path(__file__).parent / "curated"

# ── Page configuration ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Structure Validation Explorer · BEST-CSP",
    page_icon=str(ASSETS / "bestcsp-icon.png"),
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Brand colours (from BEST-CSP SVG identity) ─────────────────────────────────
# #253d8e — navy blue (text, icons)   #b0afd2 — lavender (circle motif)
st.markdown("""
<style>
/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background-color: #f4f4f8;
}

/* ── Primary buttons (Search) ── */
.stButton > button {
    background-color: #253d8e;
    color: white;
    border: none;
    font-weight: 600;
}
.stButton > button:hover {
    background-color: #1c2f6e;
    color: white;
}

/* ── Download buttons ── */
.stDownloadButton > button {
    border: 2px solid #253d8e;
    color: #253d8e;
    background-color: white;
    font-weight: 600;
}
.stDownloadButton > button:hover {
    background-color: #eef0f8;
}

/* ── Active tab indicator ── */
.stTabs [aria-selected="true"] {
    color: #253d8e !important;
    border-bottom-color: #253d8e !important;
}

/* ── Top colour bar ── */
header[data-testid="stHeader"] {
    border-top: 4px solid #253d8e;
}
</style>
""", unsafe_allow_html=True)

# ── Constants ──────────────────────────────────────────────────────────────────
COD_BASE = "https://www.crystallography.net/cod/result?"

# COD returns these raw column names; we rename them for the table
RENAME = {
    "file":    "COD ID",
    "formula": "Formula",
    "vol":     "Cell volume (Å³)",
    "Z":       "Z",
    "Zprime":  "Z′",
    "sg":      "Space group",
    "authors": "Authors",
    "journal": "Journal",
    "year":    "Year",
    "doi":     "DOI",
}

# Columns shown in the results table (others kept for deep-dive but hidden)
TABLE_COLS = ["COD ID", "Formula", "Space group", "Cell volume (Å³)", "Z", "Z′", "Density (g/cm³)"]

# ── Density helpers ────────────────────────────────────────────────────────────
# The COD REST API does not return a density field, so density is computed
# client-side from the formula, Z, and cell volume returned in the JSON.
# ρ [g/cm³] = Z × M [g/mol] / (V [Å³] × 0.60221)

# IUPAC 2021 standard atomic weights (abbreviated to elements present in COD)
_AW: dict[str, float] = {
    "H":1.008,"He":4.003,"Li":6.941,"Be":9.012,"B":10.811,"C":12.011,
    "N":14.007,"O":15.999,"F":18.998,"Ne":20.180,"Na":22.990,"Mg":24.305,
    "Al":26.982,"Si":28.086,"P":30.974,"S":32.065,"Cl":35.453,"Ar":39.948,
    "K":39.098,"Ca":40.078,"Sc":44.956,"Ti":47.867,"V":50.942,"Cr":51.996,
    "Mn":54.938,"Fe":55.845,"Co":58.933,"Ni":58.693,"Cu":63.546,"Zn":65.38,
    "Ga":69.723,"Ge":72.630,"As":74.922,"Se":78.971,"Br":79.904,"Kr":83.798,
    "Rb":85.468,"Sr":87.62,"Y":88.906,"Zr":91.224,"Nb":92.906,"Mo":95.96,
    "Tc":98.0,"Ru":101.07,"Rh":102.906,"Pd":106.42,"Ag":107.868,"Cd":112.411,
    "In":114.818,"Sn":118.710,"Sb":121.760,"Te":127.60,"I":126.904,"Xe":131.293,
    "Cs":132.905,"Ba":137.327,"La":138.905,"Ce":140.116,"Pr":140.908,"Nd":144.242,
    "Pm":145.0,"Sm":150.36,"Eu":151.964,"Gd":157.25,"Tb":158.925,"Dy":162.500,
    "Ho":164.930,"Er":167.259,"Tm":168.934,"Yb":173.054,"Lu":174.967,"Hf":178.49,
    "Ta":180.948,"W":183.84,"Re":186.207,"Os":190.23,"Ir":192.217,"Pt":195.084,
    "Au":196.967,"Hg":200.592,"Tl":204.383,"Pb":207.2,"Bi":208.980,"Po":209.0,
    "At":210.0,"Rn":222.0,"Fr":223.0,"Ra":226.0,"Ac":227.0,"Th":232.038,
    "Pa":231.036,"U":238.029,"Np":237.0,"Pu":244.0,"Am":243.0,"Cm":247.0,
    "D":2.014,  # deuterium
}

def _formula_molar_mass(formula_str: str) -> float | None:
    """
    Parse a COD formula string such as '- C6 H12 O6 -' and return the
    molar mass in g/mol, or None if any element is unrecognised.
    """
    # Strip leading/trailing dashes and whitespace used as COD delimiters
    cleaned = formula_str.strip().strip("-").strip()
    # Match element symbol (1 upper + optional lower) followed by optional count
    total = 0.0
    for m in re.finditer(r"([A-Z][a-z]?)(\d+\.?\d*)?", cleaned):
        sym, count_str = m.group(1), m.group(2)
        if sym not in _AW:
            return None
        total += _AW[sym] * (float(count_str) if count_str else 1.0)
    return total if total > 0 else None



# ── checkCIF Tutor constants ───────────────────────────────────────────────────

TUTOR_MODEL = "claude-opus-4-6"

# PLAT numeric ranges for which the structure-factor report is relevant.
# (residual density, R-factors/data quality, completeness/resolution, absolute structure)
# Geometry and ADP alerts (200–499) are NOT in this list — Mercury, not SF report.
_SF_RELEVANT_RANGES = [(1, 19), (30, 49), (80, 99)]

TUTOR_SYSTEM_PROMPT = """\
You are a teaching assistant in a one-day graduate crystallography course on
structure validation. The students are PhD-level chemists and pharmacists who
have just learned the basics of the X-ray experiment. They are using
checkCIF/PLATON to validate published crystal structures, and they come to you
when they don't understand an alert.

Your job is to help them understand what an alert means — never to tell them
whether a structure is good or bad. That judgement is the entire point of their
exercise, and you must not do it for them.

You will be given, for the alert(s) the student is asking about: the official
checkCIF description, and an "evidence pointer" telling you where a student should
look to investigate this kind of alert. Base your explanation on these. Do not
invent the meaning of an alert code; if you have not been given a definition for
it, say so.

When a student asks about an alert:
1. Translate the official description into plain language — what the test checks
   for, and what real problem it's designed to catch. The official text is
   written for experts; your job is to make it land for a curious newcomer.
2. Note what the severity level (A/B/C) signifies in general terms.
3. Point them toward the right evidence for this alert type, using the evidence
   pointer. Be specific. Crucially: not every alert is investigated in a
   structure viewer. Geometry and displacement-parameter alerts are seen in
   Mercury; residual-density, data-quality, and absolute-structure alerts are
   investigated in the checkCIF output and the structure-factor report, NOT in
   Mercury. Send them to the place the evidence actually lives.
4. End with one concrete question that pushes them to look at that evidence and
   reason about it themselves.

If the alert is one the structure-factor report speaks to (residual density,
R-factors, completeness, resolution, merging statistics), and a report is
available, you may draw on it. For alerts about molecular geometry or
displacement parameters, ignore the structure-factor report — it is not relevant
and would only distract.

Hard rules:
- Never state or imply whether the structure is trustworthy, correct,
  publishable, or "bad." If asked directly, redirect: "That's exactly what you're
  here to decide — what does the evidence tell you?"
- Keep chemistry central: many alerts are raised by statistics but resolved by
  chemical reasoning. Nudge toward "is this chemically sensible?"
- Be brief. One short explanation plus one good question beats a wall of text.

Your tone is that of a patient senior colleague who is delighted the student is
curious, and who has complete confidence they can work it out themselves with the
right nudge.\
"""


# ── Helper functions ───────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def fetch_file(url: str) -> bytes | None:
    """Download a file from COD; return bytes or None on failure."""
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.content
        return None
    except Exception:
        return None


@st.cache_data(ttl=3600)
def query_cod(query_string: str) -> pd.DataFrame:
    """Fetch CSV from COD REST API and return as a DataFrame."""
    url = COD_BASE + query_string
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(
            io.StringIO(resp.text),
            comment="#",
            low_memory=False,
        )
        if df.empty:
            return pd.DataFrame()
        return df.rename(columns=RENAME)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except Exception as exc:
        st.error(f"Error querying COD: {exc}")
        return pd.DataFrame()


def show_table(df: pd.DataFrame, sort_by: str, tab_id: str, ascending: bool = False):
    """Render the results table, download button, and deep-dive panel."""
    if df.empty:
        st.warning("No structures found. Try relaxing your filters.")
        return

    # Select available columns only (COD doesn't always return everything)
    cols = [c for c in TABLE_COLS if c in df.columns]
    # Fall back to first available column if the requested sort column is absent
    if sort_by not in cols:
        sort_by = cols[0] if cols else None
    display = df[cols].copy()
    if sort_by:
        display = display.sort_values(sort_by, ascending=ascending)
    display = display.reset_index(drop=True)

    st.success(f"Found **{len(display)}** structures.")

    col_dl, _ = st.columns([2, 6])
    with col_dl:
        st.download_button(
            "Download results as CSV",
            data=display.to_csv(index=False).encode(),
            file_name="cod_results.csv",
            mime="text/csv",
            key=f"csv_{tab_id}",
        )

    st.dataframe(display, use_container_width=True, hide_index=True)

    # ── Deep-dive panel ────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Explore a specific structure")
    st.caption(
        "Pick a COD ID below to get direct links to the entry page, "
        "the CIF file, and CheckCIF."
    )

    cod_ids = display["COD ID"].dropna().unique().tolist()
    chosen = st.selectbox("COD ID", cod_ids, key=f"dive_{tab_id}")

    if chosen:
        row = df[df["COD ID"] == chosen].iloc[0]
        has_fobs = "has Fobs" in str(row.get("flags", ""))
        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("**COD entry page**")
            st.markdown(
                f"[Open entry {chosen}](https://www.crystallography.net/cod/{chosen}.html)"
            )

        with c2:
            st.markdown("**Download files**")
            st.markdown(
                f"[{chosen}.cif](https://www.crystallography.net/cod/{chosen}.cif)"
                " — crystal structure"
            )
            if has_fobs:
                fcf_bytes = fetch_file(
                    f"https://www.crystallography.net/cod/{chosen}.hkl"
                )
                if fcf_bytes:
                    st.download_button(
                        label=f"Download {chosen}.fcf — structure factors",
                        data=fcf_bytes,
                        file_name=f"{chosen}.fcf",
                        mime="text/plain",
                        key=f"fcf_{tab_id}_{chosen}",
                    )
                    st.caption(
                        "COD stores this as .hkl but it is already in FCF (CIF) format. "
                        "The button saves it with the .fcf extension CheckCIF expects."
                    )
            else:
                st.caption("No structure factor file available for this entry in COD.")

        with c3:
            st.markdown("**CheckCIF (IUCr)**")
            st.markdown("[Open CheckCIF](https://checkcif.iucr.org/)")
            if has_fobs:
                st.caption(
                    "Upload **both** the .cif and .fcf files for a complete check "
                    "including reflection-data statistics (ALERT A/B level)."
                )
            else:
                st.caption(
                    "Upload the .cif file only. Without structure factors, "
                    "CheckCIF runs geometry checks but skips reflection-data alerts."
                )

        doi = row.get("DOI", None)
        if pd.notna(doi) and str(doi).strip() not in ("", "nan"):
            st.markdown(f"**Original paper:** [https://doi.org/{doi}](https://doi.org/{doi})")

    # ── Workflow reminder ──────────────────────────────────────────────────────
    with st.expander("Suggested workflow for each structure"):
        st.markdown("""
1. **Download the CIF** — click the link above or go to
   `https://www.crystallography.net/cod/<COD_ID>.cif`
2. **Run CheckCIF** — upload the CIF at [checkcif.iucr.org](https://checkcif.iucr.org)
   and read through the alerts carefully.
3. **Find and read the original paper** — the DOI is on the COD entry page.
4. **Form a judgment** — do the data support the reported structure?
   Is the space group assignment convincing?

> **Remember:** these structures are *interesting candidates for discussion*,
> not proof that anything is wrong.
        """)


# ── Curated-area helpers ───────────────────────────────────────────────────────

@st.cache_data
def load_curated_metadata():
    """Return list of curated structure records, or None if metadata.json is absent."""
    meta_path = CURATED / "metadata.json"
    if not meta_path.exists():
        return None
    with open(meta_path, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_evidence_pointers():
    """Return evidence-pointer rules dict, or a minimal default if file is absent."""
    ep_path = CURATED / "evidence_pointers.json"
    if not ep_path.exists():
        return {
            "default": "Look at the relevant value in the checkCIF output and ask whether it is chemically/physically reasonable.",
            "rules": [],
        }
    with open(ep_path, encoding="utf-8") as f:
        return json.load(f)


def _get_secret(key: str, default=None):
    """Return st.secrets[key] or default; never raises."""
    try:
        return st.secrets[key]
    except Exception:
        return default


@st.cache_data
def load_alert_index() -> dict:
    """Load checkcif_alerts.json and return a dict keyed by alert code."""
    json_path = Path(__file__).parent / "checkcif_reference" / "checkcif_alerts.json"
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    return {a["code"]: a for a in data["alerts"]}


def parse_alert_codes(text: str) -> list[dict]:
    """
    Extract {code, severity} pairs from pasted checkCIF text.

    Handles four formats:
      1. PLAT029_ALERT_1_C ...  (standard PLATON/IUCr underscore format, severity present)
      2. PLAT029 ALERT 1 C ...  (space-separated variant, severity present)
      3. PLAT029 ...            (bare code with PLAT prefix, no severity)
      4. 029_ALERT_1_C ...      (code without PLAT prefix — some checkCIF variants)

    Returns deduplicated list; first occurrence of each code wins for severity.
    """
    seen: dict[str, str | None] = {}

    # Pattern 1 & 2: full PLAT+code+ALERT+severity  (underscore or space separated)
    for m in re.finditer(
        r"PLAT\s*(\d{3,4})\s*[_ ]\s*ALERT\s*[_ ]\s*\d+\s*[_ ]\s*([ABCG])\b",
        text,
        re.IGNORECASE,
    ):
        code = f"PLAT{m.group(1).zfill(3)}"
        if code not in seen:
            seen[code] = m.group(2).upper()

    # Pattern 3: bare PLAT prefix only  — PLAT029 or PLAT 029
    for m in re.finditer(r"PLAT\s*(\d{3,4})", text, re.IGNORECASE):
        code = f"PLAT{m.group(1).zfill(3)}"
        if code not in seen:
            seen[code] = None

    # Pattern 4: code without PLAT prefix but followed by ALERT keyword
    # e.g. "029_ALERT_1_C" or "029 ALERT 1 C"  — seen in some checkCIF output variants
    for m in re.finditer(
        r"\b(\d{3,4})\s*[_ ]\s*ALERT\s*[_ ]\s*\d+\s*[_ ]\s*([ABCG])\b",
        text,
        re.IGNORECASE,
    ):
        code = f"PLAT{m.group(1).zfill(3)}"
        if code not in seen:
            seen[code] = m.group(2).upper()

    return [{"code": code, "severity": sev} for code, sev in seen.items()]


def lookup_evidence_pointer(code: str, ep_data: dict) -> str:
    """Return the evidence-pointer string for a PLAT code using the rules in ep_data."""
    num_match = re.search(r"\d+", code)
    if not num_match:
        return ep_data.get("default", "")
    num = int(num_match.group())
    for rule in ep_data.get("rules", []):
        if rule["match"] == "codes" and code in rule["codes"]:
            return rule["pointer"]
        if rule["match"] == "range":
            lo = int(re.search(r"\d+", rule["from"]).group())
            hi = int(re.search(r"\d+", rule["to"]).group())
            if lo <= num <= hi:
                return rule["pointer"]
    return ep_data.get("default", "Look at the relevant value in the checkCIF output.")


def is_sf_report_relevant(code: str) -> bool:
    """Return True if the SF report is relevant to investigating this PLAT code."""
    num_match = re.search(r"\d+", code)
    if not num_match:
        return False
    num = int(num_match.group())
    return any(lo <= num <= hi for lo, hi in _SF_RELEVANT_RANGES)


def _load_sf_report(record: dict) -> str | None:
    """Return the text of the structure-factor report for a curated record, or None."""
    sf_file = record.get("sf_report_file")
    if not sf_file:
        return None
    path = CURATED / sf_file
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def render_tutor(context_label: str, structure_factor_report: str | None = None):
    """
    Render the checkCIF Tutor UI: text_area input, Explain/Clear buttons, chat history.
    context_label distinguishes conversation histories across call sites.
    structure_factor_report is passed to the model only for SF-relevant alert families.
    """
    hist_key = f"_tutor_hist_{context_label}"
    if hist_key not in st.session_state:
        st.session_state[hist_key] = []

    # Display existing conversation turns
    for msg in st.session_state[hist_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["display"])

    # Input widgets
    pasted = st.text_area(
        "Paste one or more checkCIF alert lines:",
        height=130,
        key=f"_tutor_input_{context_label}",
        placeholder="e.g.  PLAT029_ALERT_1_C  or  Alert level A / PLAT213 ...",
    )
    col_explain, col_clear = st.columns([3, 1])
    with col_explain:
        explain = st.button("Explain this", key=f"_tutor_explain_{context_label}")
    with col_clear:
        if st.button("Clear conversation", key=f"_tutor_clear_{context_label}"):
            st.session_state[hist_key] = []
            st.rerun()

    if not (explain and pasted.strip()):
        return

    # ── Parse + lookup ─────────────────────────────────────────────────────────
    alerts = parse_alert_codes(pasted)
    if not alerts:
        st.warning(
            "No PLAT alert codes found. The tutor looks for codes like **PLAT029** "
            "or **PLAT029_ALERT_1_C** — paste the alert lines directly from the "
            "checkCIF output page, not just the description text."
        )
        with st.expander("Show what was pasted (helps diagnose the format)"):
            st.code(pasted, language=None)
        return

    alert_idx = load_alert_index()
    ep_data = load_evidence_pointers()

    context_lines: list[str] = []
    sf_needed = False

    for a in alerts:
        code, severity = a["code"], a["severity"]
        rec = alert_idx.get(code)
        if rec:
            sev_str = f"  Severity level: {severity}" if severity else "  Severity level: not specified in pasted text"
            context_lines += [
                f"Code: {code}",
                sev_str,
                f"  Official description: {rec['description']}",
            ]
        else:
            context_lines.append(f"Code: {code} — definition not found in the reference database.")

        pointer = lookup_evidence_pointer(code, ep_data)
        context_lines.append(f"  Evidence pointer: {pointer}")
        context_lines.append("")

        if is_sf_report_relevant(code):
            sf_needed = True

    context_block = "\n".join(context_lines).strip()

    # Build enriched API message (includes looked-up context; not shown in chat bubble)
    enriched = (
        "The student has pasted the following checkCIF alert text:\n\n"
        "---\n"
        f"{pasted}\n"
        "---\n\n"
        "Looked-up context for the extracted alert codes:\n\n"
        f"{context_block}\n"
    )
    if sf_needed and structure_factor_report:
        enriched += f"\nStructure-factor report (available for this structure):\n\n{structure_factor_report}\n"

    # Add user turn to history and display it
    st.session_state[hist_key].append({"role": "user", "display": pasted, "content": enriched})
    with st.chat_message("user"):
        st.markdown(pasted)

    # ── API call ───────────────────────────────────────────────────────────────
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
    except (KeyError, FileNotFoundError):
        api_key = None

    if not api_key:
        st.error(
            "Tutor unavailable: `ANTHROPIC_API_KEY` is not set in `.streamlit/secrets.toml`. "
            "The COD search tabs and curated file downloads still work."
        )
        st.session_state[hist_key].pop()
        return

    api_messages = [{"role": m["role"], "content": m["content"]} for m in st.session_state[hist_key]]

    try:
        client = anthropic.Anthropic(api_key=api_key)
        with st.chat_message("assistant"):
            with client.messages.stream(
                model=TUTOR_MODEL,
                max_tokens=1024,
                system=TUTOR_SYSTEM_PROMPT,
                messages=api_messages,
            ) as stream:
                response_text = st.write_stream(stream.text_stream)

        st.session_state[hist_key].append(
            {"role": "assistant", "display": response_text, "content": response_text}
        )
    except Exception as exc:
        st.error(
            f"Tutor unavailable: {exc}. "
            "The COD search tabs and curated file downloads still work."
        )
        st.session_state[hist_key].pop()


# ── One-time session-state initialisation ─────────────────────────────────────
if "reveal_unlocked" not in st.session_state:
    st.session_state["reveal_unlocked"] = bool(_get_secret("REVEAL_ENABLED", False))
if "selected_group" not in st.session_state:
    st.session_state["selected_group"] = None
if "instructor_view" not in st.session_state:
    st.session_state["instructor_view"] = False
if "_blind_mode_default" not in st.session_state:
    # Read once at startup; never re-read from secrets during the session
    st.session_state["_blind_mode_default"] = bool(_get_secret("BLIND_MODE_DEFAULT", True))
if "blind_mode" not in st.session_state:
    st.session_state["blind_mode"] = st.session_state["_blind_mode_default"]


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image(str(ASSETS / "bestcsp-logo.png"), use_container_width=True)
    st.markdown("---")
    st.markdown("### About this tool")
    st.markdown(
        """
This toolkit supports a one-day course on crystal structure validation.
It has three parts: a **COD search** for finding interesting structures,
a **curated set** of hand-picked cases with hidden teaching notes, and a
**checkCIF Tutor** that explains alerts without giving away the answer.

It is a teaching aid — **not** a quality-ranking system.
All conclusions require your own reading of the data.
        """
    )
    # ── Course setup ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Course setup")

    # Group selector — always visible; controls which curated cases are shown
    _group_choice = st.selectbox(
        "Group",
        options=["— Select your group —"] + [f"Group {i}" for i in range(1, 7)],
        key="_sidebar_group",
    )
    st.session_state["selected_group"] = (
        int(_group_choice.split()[-1])
        if _group_choice.startswith("Group")
        else None
    )

    # Reveal gate — passphrase input shown only while not yet unlocked
    _reveal_passphrase = _get_secret("REVEAL_PASSPHRASE", "")
    _passphrase_configured = bool(_reveal_passphrase)

    if not st.session_state["reveal_unlocked"]:
        if _passphrase_configured:
            _entered = st.text_input(
                "Instructor passphrase",
                type="password",
                key="_reveal_passphrase_input",
                placeholder="Instructor passphrase",
                label_visibility="collapsed",
            )
            if _entered and _entered == _reveal_passphrase:
                st.session_state["reveal_unlocked"] = True
                st.rerun()

    # Instructor controls — visible only after passphrase is entered
    if st.session_state["reveal_unlocked"]:
        st.success("Instructor access active")
        st.session_state["instructor_view"] = st.checkbox(
            "Instructor view: show all groups",
            key="_instructor_view_cb",
        )
        # In-session non-blind override (only offered when the deploy default is blind)
        if st.session_state["_blind_mode_default"]:
            _nonblind_override = st.checkbox(
                "Show pathology category inline (this session)",
                key="_nonblind_override_cb",
            )
        else:
            _nonblind_override = False
    else:
        st.session_state["instructor_view"] = False
        _nonblind_override = False

    # Derive blind_mode for this render; stored so tab4 can read it
    st.session_state["blind_mode"] = (
        st.session_state["_blind_mode_default"] and not _nonblind_override
    )

    st.markdown("---")
    st.markdown(
        "<p style='text-align:center; font-size:0.8rem; color:#555; margin-bottom:4px'>"
        "Supported by</p>",
        unsafe_allow_html=True,
    )
    st.image(str(ASSETS / "cost-logo.png"), use_container_width=True)
    st.markdown(
        "<p style='text-align:center; font-size:0.8rem; color:#555; margin-top:4px'>"
        "<a href='https://best-csp.eu/' target='_blank' style='color:#253d8e'>"
        "BEST-CSP · CA22107</a></p>",
        unsafe_allow_html=True,
    )


# ── Main page ──────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 5])
with col_logo:
    st.image(str(ASSETS / "bestcsp-icon.png"), width=80)
with col_title:
    st.markdown(
        "<h1 style='color:#253d8e; margin-bottom:0'>Crystal Structure Validation Explorer</h1>"
        "<p style='color:#b0afd2; font-size:1rem; margin-top:2px; font-weight:600'>"
        "BEST-CSP · COST Action CA22107</p>",
        unsafe_allow_html=True,
    )

st.markdown(
    "A teaching toolkit for the BEST-CSP graduate crystallography course. "
    "Search the **Crystallography Open Database** for structures worth a closer look, "
    "work through **curated cases** with known pathologies, or ask the **checkCIF Tutor** "
    "when you don't understand an alert. "
    "The goal is to develop judgement — tools here scaffold it, they don't substitute for it."
)

tab4, tab5, tab1, tab2, tab3, tab6 = st.tabs([
    "🎓 Curated structures",
    "💬 checkCIF Tutor",
    "📦 Large unit cells",
    "🔢 High Z′ structures",
    "📐 Space group P -1",
    "🪶 Density extremes",
])


# ── Tab 1: Large unit cells ────────────────────────────────────────────────────
with tab1:
    st.subheader("Structures with large unit cells")

    with st.expander("Why search for large unit cells?", expanded=True):
        st.markdown("""
A large unit cell is not a problem in itself — many complex materials have huge cells.
But for chemically simple systems a very large cell can indicate:

- **Missed symmetry**: the true cell may be a fraction of the reported one
- **Pseudo-symmetry**: the structure refines well in a low-symmetry setting
  but a higher-symmetry model also fits the data
- **Disorder or solvent inclusion**: making the asymmetric unit unexpectedly large

These structures are good starting points for a PLATON/ADDSYM exercise.
        """)

    c1, c2, c3 = st.columns(3)
    with c1:
        vmin = st.slider(
            "Minimum cell volume (Å³)",
            min_value=1_000, max_value=50_000, value=5_000, step=500,
            key="vmin1",
        )
    with c2:
        el_max = st.slider(
            "Maximum number of elements",
            min_value=1, max_value=8, value=3, step=1,
            key="elmax1",
            help="Limit to chemically simple systems to focus on potential symmetry issues.",
        )
    with c3:
        organic_only1 = st.checkbox(
            "Organic structures only (must contain C)",
            value=False,
            key="org1",
        )

    if st.button("Search", key="btn1"):
        el_filter = "&el1=C" if organic_only1 else ""
        q = f"format=csv&vmin={vmin}&vmax=1000000&strictmin=1&strictmax={el_max}{el_filter}"
        with st.spinner("Querying COD…"):
            st.session_state["df1"] = query_cod(q)

    fobs1 = st.checkbox("Only structures with structure factors (FCF) available", key="fobs1")

    if "df1" in st.session_state:
        df1 = st.session_state["df1"]
        if fobs1 and "flags" in df1.columns:
            df1 = df1[df1["flags"].str.contains("has Fobs", na=False)]
        show_table(df1, sort_by="Cell volume (Å³)", tab_id="tab1", ascending=False)


# ── Tab 2: High Z′ structures ──────────────────────────────────────────────────
with tab2:
    st.subheader("Structures with high Z′")

    with st.expander("Why search for high Z′?", expanded=True):
        st.markdown("""
**Z′** is the number of independent formula units in the asymmetric unit.
Most small-molecule structures have Z′ = 1; Z′ > 1 is unusual and can arise from:

- **Pseudo-symmetry**: two or more molecules are nearly — but not exactly — symmetry-equivalent.
  Sometimes a higher-symmetry refinement is possible.
- **Multiple conformers or polymorphic co-existence** captured in a single crystal
- **Co-crystals or solvates** with several independent species
- **Phase transitions**: a low-temperature phase sometimes "remembers" the high-T cell

High Z′ is not wrong — but it deserves scrutiny.
Compare the independent molecules: are they really different, or almost identical?
        """)

    c1, c2 = st.columns(2)
    with c1:
        zprime_min = st.selectbox(
            "Minimum Z′",
            options=[2, 3, 4, 5, 6, 8, 10],
            index=1,
            key="zp2",
        )
    with c2:
        organic_only2 = st.checkbox(
            "Organic structures only (must contain C)",
            value=True,
            key="org2",
        )

    if st.button("Search", key="btn2"):
        el_filter = "&el1=C" if organic_only2 else ""
        q = f"format=csv&minZprime={zprime_min}{el_filter}"
        with st.spinner("Querying COD…"):
            st.session_state["df2"] = query_cod(q)

    fobs2 = st.checkbox("Only structures with structure factors (FCF) available", key="fobs2")

    if "df2" in st.session_state:
        df2 = st.session_state["df2"]
        if fobs2 and "flags" in df2.columns:
            df2 = df2[df2["flags"].str.contains("has Fobs", na=False)]
        show_table(df2, sort_by="Z′", tab_id="tab2", ascending=False)


# ── Tab 3: Space group P -1 ────────────────────────────────────────────────────
with tab3:
    st.subheader("Structures in space group P -1 (triclinic)")

    with st.expander("Why look at P -1 structures?", expanded=True):
        st.markdown("""
**P -1** (triclinic, symmetry elements: identity + inversion) is the lowest possible
symmetry for a crystal. Many correct structures genuinely belong in P -1.
However, it is also the "space group of last resort":
if you cannot find any other symmetry, P -1 always works.

Questions worth asking for a P -1 structure:
- Does PLATON/ADDSYM suggest any missed symmetry?
- Are the cell angles close to 90°? (Possible monoclinic or orthorhombic metric)
- Is Z′ > 1? (Possible pseudo-symmetry)
- Is the R-factor acceptable, or unusually high?

**Note:** P -1 is space group number 2 in the International Tables.
Space group P 1 (number 1, no symmetry at all) is different and extremely rare.
        """)

    c1, c2, c3 = st.columns(3)
    with c1:
        vmin3 = st.slider(
            "Minimum cell volume (Å³)",
            min_value=0, max_value=10_000, value=0, step=200,
            key="vmin3",
        )
    with c2:
        el_max3 = st.slider(
            "Maximum number of elements",
            min_value=1, max_value=8, value=5, step=1,
            key="elmax3",
        )
    with c3:
        organic_only3 = st.checkbox(
            "Organic structures only (must contain C)",
            value=True,
            key="org3",
        )

    sort3 = st.radio(
        "Sort results by",
        ["Cell volume (Å³)", "Z′", "Z"],
        horizontal=True,
        key="sort3",
    )

    if st.button("Search", key="btn3"):
        el_filter = "&el1=C" if organic_only3 else ""
        vol_filter = f"&vmin={vmin3}" if vmin3 > 0 else ""
        q = (
            f"format=csv&space_group_number=2"
            f"&strictmin=1&strictmax={el_max3}"
            f"{vol_filter}{el_filter}"
        )
        with st.spinner("Querying COD…"):
            st.session_state["df3"] = query_cod(q)

    fobs3 = st.checkbox("Only structures with structure factors (FCF) available", key="fobs3")

    if "df3" in st.session_state:
        df3 = st.session_state["df3"]
        if fobs3 and "flags" in df3.columns:
            df3 = df3[df3["flags"].str.contains("has Fobs", na=False)]
        show_table(df3, sort_by=sort3, tab_id="tab3", ascending=False)


# ── Tab 4: Curated structures ──────────────────────────────────────────────────
with tab4:
    st.subheader("Curated teaching structures")
    st.caption(
        "These structures have been hand-picked for the course. "
        "Download the files, run CheckCIF, and form your own judgement "
        "before opening the teaching note."
    )

    curated_meta = load_curated_metadata()

    if curated_meta is None:
        st.info(
            "No curated structures found. To add structures, create "
            "`curated/metadata.json` in the app directory and populate it "
            "with structure records — see the README for the schema."
        )
    else:
        # Resolve group / instructor-view state (set by sidebar)
        _sel_group = st.session_state["selected_group"]       # None or 1–6
        _reveal_on = st.session_state["reveal_unlocked"]       # bool
        _instr_view = st.session_state["instructor_view"] and _reveal_on  # defence-in-depth

        # Filter visible cases
        if _instr_view:
            visible = curated_meta                             # all cases
        elif _sel_group is not None:
            visible = [
                s for s in curated_meta
                if _sel_group in s.get("assigned_groups", [])
            ]
        else:
            visible = None                                     # prompt to select group

        if visible is None:
            st.info("Please select your group in the sidebar to see your cases.")
        elif len(visible) == 0:
            st.info(
                f"No cases are currently assigned to Group {_sel_group}. "
                "Ask the instructor."
            )
        else:
            # Selectbox: show label only in instructor view
            if _instr_view:
                labels = [f"{s['label']} — {s['title']}" for s in visible]
            else:
                labels = [s["title"] for s in visible]
            chosen_idx = st.selectbox(
                "Select a structure",
                range(len(labels)),
                format_func=lambda i: labels[i],
                key="curated_select",
            )

            st.markdown("---")
            s = visible[chosen_idx]
            _blind = st.session_state["blind_mode"]

            # ── Title ──────────────────────────────────────────────────────────
            st.markdown(
                f"<h3 style='color:#253d8e; margin-bottom:4px'>{s['title']}</h3>",
                unsafe_allow_html=True,
            )
            # Pathology category — inline only in non-blind mode
            if not _blind:
                st.markdown(f"**Pathology category:** {s['pathology_category']}")

            # ── Download buttons + CheckCIF link ───────────────────────────────
            col_cif, col_fcf, col_cc = st.columns(3)

            cif_path = CURATED / s["cif_file"]
            with col_cif:
                if cif_path.exists():
                    st.download_button(
                        label="Download CIF" if not _instr_view else f"Download {s['label']}.cif",
                        data=cif_path.read_bytes(),
                        file_name=f"{s['label']}.cif",
                        mime="text/plain",
                        key=f"dl_cif_{s['label']}",
                    )
                else:
                    st.caption(f"CIF file not found: {s['cif_file']}")

            with col_fcf:
                fcf_rel = s.get("fcf_file")
                if fcf_rel:
                    fcf_path = CURATED / fcf_rel
                    if fcf_path.exists():
                        st.download_button(
                            label="Download FCF" if not _instr_view else f"Download {s['label']}.fcf",
                            data=fcf_path.read_bytes(),
                            file_name=f"{s['label']}.fcf",
                            mime="text/plain",
                            key=f"dl_fcf_{s['label']}",
                        )
                    else:
                        st.caption(f"FCF listed but not found: {fcf_rel}")
                else:
                    st.caption("No structure factor file for this entry.")

            with col_cc:
                st.markdown("**Run CheckCIF**")
                st.markdown("[Open CheckCIF (IUCr)](https://checkcif.iucr.org/)")
                if s.get("fcf_file"):
                    st.caption(
                        "Upload **both** the .cif and .fcf files for a complete "
                        "check including reflection-data statistics."
                    )
                else:
                    st.caption(
                        "Upload the .cif file only. Without structure factors, "
                        "CheckCIF runs geometry checks but skips reflection-data alerts."
                    )

            # ── Tutor (unaffected by blind_mode or reveal state) ────────────────
            st.markdown("---")
            st.markdown("#### Ask the checkCIF Tutor about an alert")
            render_tutor(
                context_label=f"curated__{s['label']}",
                structure_factor_report=_load_sf_report(s),
            )

            st.markdown("---")

            # ── Hint expander — blind mode only ────────────────────────────────
            if _blind:
                with st.expander("Need a hint?"):
                    st.markdown(f"**Pathology category:** {s['pathology_category']}")

            # ── Teaching note expander ─────────────────────────────────────────
            # Files under curated/teaching_notes/ are NEVER read when _reveal_on
            # is False — no other code path touches them.
            with st.expander("Open only after you've made your call"):
                if _reveal_on:
                    note_file = s.get("teaching_note_file")
                    if note_file:
                        note_path = CURATED / note_file
                        if note_path.exists():
                            st.markdown(note_path.read_text(encoding="utf-8"))
                        else:
                            st.warning(
                                f"No teaching note found at `{note_file}`. "
                                "Add the file or update `teaching_note_file` in metadata.json."
                            )
                    else:
                        st.info("No teaching note file is specified for this structure.")
                else:
                    st.markdown(
                        "*Teaching notes will be revealed during the group discussion.*"
                    )

            # ── Instructor badge bar — never shown to students ─────────────────
            if _instr_view:
                st.markdown("---")
                groups = s.get("assigned_groups", [])
                if groups:
                    grp_badge = (
                        "All groups"
                        if len(groups) == 6
                        else f"Groups {', '.join(str(g) for g in sorted(groups))}"
                    )
                else:
                    grp_badge = "Unassigned (reserve)"
                parts = [
                    f"label: `{s['label']}`",
                    f"source: {s.get('source_route', '—')}",
                    f"groups: {grp_badge}",
                ]
                if s.get("citation"):
                    parts.append(f"citation: {s['citation']}")
                doi = s.get("doi")
                if doi:
                    parts.append(f"DOI: [link](https://doi.org/{doi})")
                if s.get("deposited_id"):
                    parts.append(f"deposited ID: {s['deposited_id']}")
                st.caption("Instructor info — " + " · ".join(parts))


# ── Tab 5: checkCIF Tutor (standalone) ────────────────────────────────────────
with tab5:
    st.subheader("checkCIF Tutor")
    st.markdown(
        "Paste one or more alert lines from your checkCIF report below. "
        "The tutor will explain what each alert means and point you toward "
        "the right evidence — it will not tell you whether the structure is "
        "good or bad. That judgement is yours."
    )
    render_tutor(context_label="standalone")


# ── Tab 6: Density extremes ───────────────────────────────────────────────────
with tab6:
    st.subheader("Structures with unusual density")

    _DENSITY_MODES = {
        "Low (< 1.0 g/cm³)":  ("low",    None,  1.0,  "Often a sign of unmodelled solvent or void space — the SQUEEZE territory."),
        "High (> 2.5 g/cm³)": ("high",   2.5,   None, "For all-light-atom organics, surprisingly high density can indicate misassigned heavy atoms or scattering-factor errors."),
        "Custom range…":       ("custom", None,  None, "Define your own range to explore the density distribution."),
    }

    d_mode_label = st.radio(
        "Density filter",
        list(_DENSITY_MODES.keys()),
        horizontal=True,
        key="d_mode",
    )
    mode_key, d_lo_preset, d_hi_preset, caption = _DENSITY_MODES[d_mode_label]
    st.caption(f"*{caption}*")

    if mode_key == "custom":
        cd1, cd2 = st.columns(2)
        with cd1:
            d_lo_input = st.number_input("Min density (g/cm³)", min_value=0.0, value=0.0,
                                          step=0.1, key="d_lo")
        with cd2:
            d_hi_input = st.number_input("Max density (g/cm³)", min_value=0.0, value=5.0,
                                          step=0.1, key="d_hi")
        d_lo = d_lo_input if d_lo_input > 0 else None
        d_hi = d_hi_input if d_hi_input > 0 else None
    else:
        d_lo, d_hi = d_lo_preset, d_hi_preset

    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        d_vmin = st.number_input(
            "Minimum cell volume (Å³)",
            min_value=100, value=500, step=100, key="d_vmin",
            help="Required — prevents the query from returning an unmanageably large result set.",
        )
        if d_vmin < 100:
            d_vmin = 500
    with dc2:
        d_nel_max = st.slider(
            "Maximum number of elements",
            min_value=1, max_value=8, value=4, step=1, key="d_nel",
        )
    with dc3:
        d_sg = st.text_input("Space group (optional)", key="d_sg",
                              placeholder="e.g. P 21/c")

    if st.button("Search", key="btn_density"):
        # COD JSON endpoint silently returns [] for large result sets, so use
        # the same CSV path as the other tabs via query_cod(), then compute
        # density client-side from the Formula, Z, and Cell volume columns.
        sg_param = f"&spacegroup={d_sg.strip()}" if d_sg.strip() else ""
        q = f"format=csv&vmin={d_vmin}&strictmin=1&strictmax={d_nel_max}{sg_param}"
        with st.spinner("Querying COD…"):
            st.session_state["density_df"] = query_cod(q)

    if "density_df" in st.session_state:
        df_all = st.session_state["density_df"]
        if df_all.empty:
            st.warning("No structures returned. Try relaxing your filters.")
        else:
            def _row_density(row) -> float | None:
                try:
                    z   = float(row.get("Z") or 0)
                    vol = float(row.get("Cell volume (Å³)") or 0)
                    if z <= 0 or vol <= 0:
                        return None
                    mw = _formula_molar_mass(str(row.get("Formula") or ""))
                    if mw is None:
                        return None
                    return round((z * mw) / (vol * 0.60221), 3)
                except (TypeError, ValueError):
                    return None

            df_all = df_all.copy()
            df_all["Density (g/cm³)"] = df_all.apply(_row_density, axis=1)

            n_total  = len(df_all)
            skipped  = int(df_all["Density (g/cm³)"].isna().sum())
            df_valid = df_all.dropna(subset=["Density (g/cm³)"])

            if d_lo is not None:
                df_valid = df_valid[df_valid["Density (g/cm³)"] >= d_lo]
            if d_hi is not None:
                df_valid = df_valid[df_valid["Density (g/cm³)"] <= d_hi]

            st.info(
                f"**{len(df_valid)}** of **{n_total}** structures match the density filter."
                + (f" {skipped} skipped (formula unreadable or missing)." if skipped else "")
            )

            if not df_valid.empty:
                show_table(df_valid, sort_by="Density (g/cm³)", tab_id="tab_density",
                           ascending=(mode_key == "low"))


# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    "<p style='text-align:center; font-size:0.8rem; color:#888'>"
    "Data from the <a href='https://www.crystallography.net/cod/' style='color:#253d8e'>Crystallography Open Database</a> · "
    "Developed for the <a href='https://best-csp.eu/' style='color:#253d8e'>BEST-CSP COST Action CA22107</a> · "
    "Educational use only"
    "</p>",
    unsafe_allow_html=True,
)
