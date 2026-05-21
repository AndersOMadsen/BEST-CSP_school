# Crystallography Teaching Materials — Bucharest Best-CSP School

Teaching materials for a crystallography session focused on evaluating crystal structures
from the Crystallography Open Database (COD). The emphasis is on developing critical
judgment — finding structures that deserve a closer look, not on automated quality scoring.

---

## Contents

| Folder | What it contains |
|---|---|
| `streamlit_app/` | Interactive web app for exploring the COD |
| `notebooks/` | Jupyter notebook with the same queries, step by step |
| `scripts/` | Command-line tool for batch CIF download and CheckCIF |
| `examples/` | Sample CIF file and CheckCIF report for one structure |

---

## The three tools and when to use each

### 1. Streamlit web app — for the classroom session

The app lets students explore COD structures through a browser with no coding required.
It is the primary teaching tool for the session.

**[→ Open the live app](https://your-app-name.streamlit.app)**
*(replace this link once deployed — see deployment instructions below)*

Three search types are available:

- **Large unit cells** — structures where the cell may be larger than the true symmetry requires
- **High Z′ structures** — multiple independent molecules in the asymmetric unit
- **Space group P -1** — the lowest-symmetry triclinic setting; often correct, sometimes not

Each search returns a table of structures with direct links to the COD entry,
the CIF file, CheckCIF, and the original paper.

---

### 2. Jupyter notebook — for self-paced learning or homework

`notebooks/COD_Search_Notebook.ipynb` walks through the same three queries as the app,
but as executable Python cells with explanatory markdown.

Suitable for:
- Students who want to understand what is happening under the hood
- Homework or follow-up exercises after the classroom session
- Instructors who want to adapt or extend the queries

**Prerequisites:** Python 3.9+, `pandas`, `jupyter` (or JupyterLab).

```bash
pip install pandas jupyter
jupyter notebook notebooks/COD_Search_Notebook.ipynb
```

---

### 3. Command-line batch checker — for advanced use

`scripts/cod_checker.py` automates the process of downloading CIFs and submitting them
to CheckCIF in bulk. Useful for instructors preparing examples, or students who want to
check a list of structures they found interesting.

**Prerequisites:** Python 3.9+, `pandas`, `requests`, `tqdm`.

```bash
pip install pandas requests tqdm
```

**Basic usage — check a few structures by ID:**

```bash
python scripts/cod_checker.py 1000510 1000004 1100404
```

**Check a list of IDs from a text file:**

```bash
# ids.txt contains one COD ID per line
python scripts/cod_checker.py -f ids.txt -o my_results/
```

Output is saved to the specified folder (default: `cod_checks/`):

| File | Contents |
|---|---|
| `<COD_ID>.cif` | The downloaded CIF file |
| `checkcif_<COD_ID>.html` | The full CheckCIF HTML report |
| `summary.csv` | One row per structure: ID, CIF status, CheckCIF status, DOI |

See `examples/1000510_sample/` for sample output from a single structure.

---

## Suggested workflow for students

The app and notebook help you find *candidates for inspection*. This is what to do next:

1. **Download the CIF** from the COD entry page or directly:
   `https://www.crystallography.net/cod/<COD_ID>.cif`

2. **Run CheckCIF** at [checkcif.iucr.org](https://checkcif.iucr.org).
   Read the alerts — understand what each level (A, B, C, G) means.

3. **Find and read the original paper.**
   The DOI is on the COD entry page.

4. **Form a judgment.**
   Does the reported structure make chemical and crystallographic sense?
   Is the space group assignment convincing?
   Are there unaddressed alerts in CheckCIF?

> These structures are **interesting discussion candidates**, not proven errors.
> Always read the paper before drawing conclusions.

---

## Running the Streamlit app locally

```bash
cd streamlit_app
pip install -r requirements.txt
streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## Deploying the app to Streamlit Community Cloud

1. Push this repository to GitHub (see below).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **New app**.
4. Select your repository, branch (`main`), and set the **Main file path** to
   `streamlit_app/app.py`.
5. Click **Deploy**.

Streamlit Cloud reads `streamlit_app/requirements.txt` automatically.
No further configuration is needed. The live URL can be shared directly with students.

---

## Pushing this repository to GitHub

If you have already initialised the local git repo:

```bash
# Create a new empty repository on github.com, then:
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

---

## Repository structure

```
.
├── README.md
├── .gitignore
├── streamlit_app/
│   ├── app.py
│   └── requirements.txt
├── notebooks/
│   └── COD_Search_Notebook.ipynb
├── scripts/
│   └── cod_checker.py
└── examples/
    └── 1000510_sample/
        ├── 1000510.cif
        ├── checkcif_1000510.html
        └── summary.csv
```

---

## Data source

All structure data comes from the
[Crystallography Open Database (COD)](https://www.crystallography.net/cod/),
an open-access repository of crystal structures.
Gražulis *et al.*, *J. Appl. Cryst.* **2009**, *42*, 726–729.

---

*Anders Ø. Madsen — University of Copenhagen*
