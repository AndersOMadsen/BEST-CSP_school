import streamlit as st
import pandas as pd
import requests
import io
from pathlib import Path

# Always resolve asset paths relative to this file, regardless of working directory
ASSETS = Path(__file__).parent / "assets"

# ── Page configuration ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="COD Structure Explorer · BEST-CSP",
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
TABLE_COLS = ["COD ID", "Formula", "Space group", "Cell volume (Å³)", "Z", "Z′"]


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


def show_table(df: pd.DataFrame, sort_by: str, ascending: bool = False):
    """Render the results table, download button, and deep-dive panel."""
    if df.empty:
        st.warning("No structures found. Try relaxing your filters.")
        return

    # Select available columns only (COD doesn't always return everything)
    cols = [c for c in TABLE_COLS if c in df.columns]
    display = df[cols].sort_values(sort_by, ascending=ascending).reset_index(drop=True)

    st.success(f"Found **{len(display)}** structures.")

    col_dl, _ = st.columns([2, 6])
    with col_dl:
        st.download_button(
            "Download results as CSV",
            data=display.to_csv(index=False).encode(),
            file_name="cod_results.csv",
            mime="text/csv",
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
    chosen = st.selectbox("COD ID", cod_ids, key=f"dive_{sort_by}")

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
                        key=f"fcf_{chosen}",
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


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image(str(ASSETS / "bestcsp-logo.png"), use_container_width=True)
    st.markdown("---")
    st.markdown("### About this tool")
    st.markdown(
        """
This app queries the
[Crystallography Open Database (COD)](https://www.crystallography.net/cod/)
and surfaces structures that may reward closer inspection.

It is a teaching aid — **not** a quality-ranking system.
All conclusions require reading the original paper and checking the data.
        """
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
        "<h1 style='color:#253d8e; margin-bottom:0'>COD Crystal Structure Explorer</h1>"
        "<p style='color:#b0afd2; font-size:1rem; margin-top:2px; font-weight:600'>"
        "BEST-CSP · COST Action CA22107</p>",
        unsafe_allow_html=True,
    )

st.markdown(
    "Find crystal structures from the **Crystallography Open Database** that are worth "
    "a second look — not because they are wrong, but because they raise interesting "
    "crystallographic questions. Choose a search type, adjust the filters, and click **Search**."
)

tab1, tab2, tab3 = st.tabs([
    "📦 Large unit cells",
    "🔢 High Z′ structures",
    "📐 Space group P -1",
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
        if fobs1:
            df1 = df1[df1["flags"].str.contains("has Fobs", na=False)]
        show_table(df1, sort_by="Cell volume (Å³)", ascending=False)


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
        if fobs2:
            df2 = df2[df2["flags"].str.contains("has Fobs", na=False)]
        show_table(df2, sort_by="Z′", ascending=False)


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
        st.session_state["sort3"] = sort3

    fobs3 = st.checkbox("Only structures with structure factors (FCF) available", key="fobs3")

    if "df3" in st.session_state:
        df3 = st.session_state["df3"]
        if fobs3:
            df3 = df3[df3["flags"].str.contains("has Fobs", na=False)]
        show_table(df3, sort_by=st.session_state.get("sort3", "Cell volume (Å³)"), ascending=False)


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
