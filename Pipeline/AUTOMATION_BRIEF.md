# Claude Code brief — degradation → refinement → validation automation

## 0. What this is

A **local, headless batch pipeline** (NOT part of the Streamlit app) that takes a
set of correct, refined crystal structures and produces a "ladder" of
deliberately data-degraded versions, re-refines each with SHELXL, assembles a
clean CIF, validates locally with PLATON, and emits **one consolidated summary
table per structure** for the instructor to verify.

This is a teaching-asset generator. The instructor will double-check every
result; your job is to make that check tractable, not to replace it.

## 1. Fixed inputs you are given (do not regenerate)

- `degrade_data.py` — existing, working script that generates degraded HKLF4
  files (resolution truncation, completeness reduction, wedge removal, weak-data,
  absorption-error injection) and writes per-rung directories with a copied
  `.ins` and a `DEGRADATION.txt` stamp. **Reuse it as a library / subprocess; do
  not rewrite its degradation maths.** Read it to learn its `RUNGS` mechanism and
  its HKL I/O.
- `DEGRADATION_PROTOCOL.md` — the protocol and the verified checkCIF/PLATON alert
  map. The summary table you produce should align with the "what each rung should
  make checkCIF say" table in this document.
- Per structure: a directory containing the **published Acta E CIF** (ground
  truth, with embedded data, DOI, refinement stats), and the instructor's
  **command-line SHELXL** inputs/outputs (`.ins`, `.hkl`, `.res`, `.fcf`, `.lst`)
  from a converged refinement run with the `ACTA` instruction (so the FCF is LIST
  4 type).

## 2. Environment (confirmed available)

- `shelxl` at `/usr/local/bin/shelxl`
- `platon` at `/usr/local/bin/platon`
- Python with `gemmi` and `numpy` available.
- PLATON validation is invoked as: **`platon -u <name>.cif`** → produces
  `<name>.chk` (main report) and `<name>.ckf` (reflection-data analysis).
  **Both files must be kept and parsed** — the `.ckf` carries the
  residual-density / completeness / missing-reflection diagnostics that are the
  whole point of the absorption and wedge rungs.
- PLATON needs `check.def` in the working dir OR the `CHECKDEF` env var pointing
  at it. Detect/locate it; if absent, fail loudly with a clear message rather
  than producing a silently-incomplete report.

## 3. The per-structure pipeline

For each structure directory:

### 3.1 Rung 0 control
Confirm the instructor's converged refinement exists. Validate it (`platon -u`)
to capture the **baseline alerts of the untouched structure** — these are part of
the lesson (especially for Cu structures, see §5). Record them in the summary as
"reference".

### 3.2 Generate rungs
Call `degrade_data.py` with the per-structure cell and the structure's `RUNGS`
config (see §5 — the config is per-structure and split by radiation; do NOT apply
a uniform ladder across all structures). This produces `rung_*/` dirs each with a
degraded `<name>.hkl` and a copied `<name>.ins` (with `LIST 4` ensured).

### 3.3 Refine each rung
In each rung dir run `shelxl <name>` to convergence against the degraded data.
**Do NOT modify the model between rungs** — same atoms, same disorder model, same
restraints as the correct structure. The point is to watch a *correct model*
react to *bad data*. Capture `.res`, `.fcf`, `.lst`.

### 3.4 Assemble a clean CIF with gemmi  (route b — this is the crux)
For each rung, build a PLATON-clean CIF by **merging the published CIF's header
metadata with this rung's SHELXL refinement results**:
- Take cell, symmetry, **radiation type and wavelength**, temperature, and other
  experimental header fields from the **published CIF** (each structure keeps its
  own — see §5, Cu vs Mo wavelengths differ and a wrong wavelength fires a
  spurious PLAT-wavelength Type_1 alert).
- Take refinement results (coordinates, ADPs, R-factors, etc.) and the embedded
  `.res`/`.hkl` from this rung's SHELXL output.
- **Preserve the embedded `.res` and `.hkl` blocks in the CIF** — PLATON's
  documentation explicitly warns not to remove them; full FCF validation depends
  on them.
- Pair the CIF with this rung's LIST 4 `.fcf`.

> Verify the exact gemmi CIF read/write/merge API against the installed gemmi
> version at build time (check `gemmi.cif` document/block handling) rather than
> assuming call signatures. Confirm the assembled CIF round-trips through
> `platon -u` without construction/syntax (Type_1) alerts on the *reference* rung
> — if Rung 0 throws CIF-construction alerts, the merge is wrong and must be fixed
> before trusting any degraded rung.

### 3.5 Validate locally
Run `platon -u <name>.cif` in each rung dir. Keep `.chk` and `.ckf`. Parse both
for the `ALERT_n_mxx` lines: extract code, level (A/B/C/G), type, and the message.

### 3.6 Summary table (the primary deliverable)
Emit **one table per structure** (CSV + a readable Markdown version) with one row
per rung and columns for: rung tag, degradation op (from `DEGRADATION.txt`), key
refinement stats (R1, wR2, data/parameter ratio, completeness, highest residual
density peak, resolution), and the alerts fired with their levels. The instructor
reads 7 tables, not ~56 raw reports.

Also flag, per rung, any alert that is **NOT** attributable to the intended
degradation (e.g. a stray Type_1 metadata alert), so the instructor can see at a
glance whether the signal is clean.

## 4. Guardrails — do NOT do these

- **Do NOT submit anything to the IUCr checkCIF web service.** There is no public
  batch API; automated submission is brittle and discouraged. Validation is
  LOCAL via `platon -u` only.
- **Do NOT re-optimise / change the model between rungs** to "fix" degraded data.
  Same atoms throughout. Allowing the least-squares to converge is fine; changing
  the atom list, disorder model, or restraints is not.
- **Do NOT validate against the published CIF** as if it were your result — it is
  ground truth / the answer, used only as the source of header metadata and for
  the reveal. Your alerts come from *your* re-refined rungs.
- **Do NOT apply a uniform RUNGS ladder** across structures — it is per-structure
  and radiation-dependent (§5).
- **Do NOT strip the embedded .res/.hkl** from assembled CIFs.
- **Do NOT hardcode a single wavelength/radiation** — carry each structure's own
  from its published CIF.
- Preserve every `DEGRADATION.txt` provenance stamp; propagate the op string into
  the summary and (later) into the app's `metadata.json`.

## 5. Per-structure config — radiation matters

There are 7 structures (6 in use + 1 reserve). Some are **Cu Kα** (λ≈1.5418 Å,
d_max≈0.8 Å — little headroom to truncate resolution) and some **Mo Kα**
(λ≈0.71073 Å, higher resolution — real room to truncate). Build a small
per-structure config file (e.g. `structures.yaml` or `.json`) the instructor
edits, holding for each: name, path, cell, radiation, and its `RUNGS` list.

Guidance to bake into the config template and its comments:
- **Cu / ~0.8 Å structures:** resolution truncation is a weak lever (almost no
  headroom). Lean on completeness, wedge, and weak-data rungs. Their *reference*
  rung may already carry a mild completeness flavour — inspect, don't assume
  clean.
- **Mo / high-res structures:** full resolution ladder available (e.g. d_min 1.0,
  1.2 Å), plus the same completeness/wedge/weak/absorption rungs.
- Completeness levels are threshold-sharp (<95% C, <90% B, <85% A); target final
  completeness just inside the desired band and confirm the *actual* value from
  the report.

## 6. Deliverables

- An orchestrator script (e.g. `run_ladder.py`) driving the per-structure
  pipeline end to end, reading `structures.yaml`.
- A `structures.yaml` template with all 7 structures stubbed and commented.
- A gemmi-based CIF-assembly module (the §3.4 merge), verified against the
  installed gemmi and confirmed PLATON-clean on a reference rung.
- A PLATON `.chk`/`.ckf` parser producing the per-structure summary (CSV + MD).
- A short README: prerequisites, how to add a structure, how to set CHECKDEF,
  how to read the summary, and the explicit reminder that the instructor must
  verify results and that these are deliberately degraded teaching artefacts.
