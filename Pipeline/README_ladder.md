# Degradation ladder pipeline

A local, headless batch tool that takes correct crystal structures, degrades their
data in a graded series, re-refines each rung with SHELXL, validates with PLATON,
and emits a consolidated summary table per structure.

**The instructor must verify every result.** This pipeline generates teaching
artefacts; it does not replace crystallographic judgement.

---

## Prerequisites

```bash
pip install pyyaml gemmi numpy
```

External programs (must be on PATH or at the hardcoded paths in `run_ladder.py`):

| Program | Expected path | Notes |
|---|---|---|
| `shelxl` | `/usr/local/bin/shelxl` | Multi-CPU version recommended |
| `platon` | `/usr/local/bin/platon` | Runs headless with `DISPLAY=` |

PLATON needs its `check.def` definition file. It usually locates it automatically.
If validation produces an empty or truncated `.chk`, see [CHECKDEF](#checkdef) below.

---

## Quick start

```bash
# 1. Generate all rung directories (writes degraded HKL + copied INS files)
python run_ladder.py --steps generate

# 2. Refine each rung with SHELXL
python run_ladder.py --steps refine

# 3. Merge published CIF header with SHELXL output
python run_ladder.py --steps assemble

# 4. Validate with PLATON
python run_ladder.py --steps validate

# 5. Parse .chk files → ladder/summary.csv + summary.md
python run_ladder.py --steps summarize

# Or run everything in one go:
python run_ladder.py

# Only process specific structures:
python run_ladder.py ej2019 wm5793

# Preview what would run without writing or executing anything:
python run_ladder.py --dry-run
```

After a successful run, each structure's `Good_Structures_and_data/<id>/ladder/`
directory contains:

```
ladder/
├── summary.csv          ← one row per rung, machine-readable
├── summary.md           ← same table in Markdown, instructor-readable
└── rung_00_reference/
│   ├── I.hkl            ← degraded reflection data (reference = untouched)
│   ├── I.ins            ← correct model (unchanged throughout)
│   ├── I.res            ← SHELXL output
│   ├── I.fcf            ← LIST 4 FCF (for full PLATON validation)
│   ├── I.cif            ← merged CIF (published header + SHELXL results)
│   ├── I.chk            ← PLATON report
│   ├── I.ckf            ← PLATON FCF-validation report
│   └── DEGRADATION.txt  ← provenance stamp (keep this)
├── rung_01_res_1p0/
│   └── ...
└── ...
```

---

## How to read the summary table

Each row is one rung. Key columns:

| Column | What it tells you |
|---|---|
| `rung` | Rung tag (e.g. `03_complete_88`) |
| `op` | Degradation operation applied |
| `R1` / `wR2` / `GooF` | Refinement quality indicators — watch these climb |
| `data_param_ratio` | Nref/Npar — below ~10 the refinement becomes underdetermined |
| `completeness` | Fraction of expected unique reflections present |
| `rho_max` | Highest residual density peak (e/Å³) — absorption rung signature |
| `resolution_A` | Effective d_min (Å) from PLATON FCF analysis |
| `alerts_A/B/C/G` | PLATON alert counts by severity |
| `new_alert_codes` | Alert codes present in this rung but absent in the reference rung |
| `unexpected_type1` | Type-1 (CIF construction) alerts that are new in this rung |

**Instructor check:** the `unexpected_type1` column must be empty for all degraded
rungs. If it has entries, the CIF assembly step produced a malformed CIF — fix
`assemble_cif.py` and re-run `assemble` + `validate` + `summarize`.

The reference rung (`00_reference`) establishes the baseline noise floor: any alert
present there is an inherent property of the source structure, not a degradation
artefact. Only `new_alert_codes` in the degraded rungs are the teaching signal.

Alert mapping (from `DEGRADATION_PROTOCOL.md`):

| Rung type | Expected new alerts |
|---|---|
| Resolution truncation | PLATON RRTP family (data/parameter ratio), resolution-limit alerts |
| Completeness (random) | REFLT03 family, PLAT022, PLAT029 |
| Wedge | Same as completeness + direction-dependent missing-reflection listing |
| Wedge (low-angle biased) | Above + theta_full < theta_max signature |
| Weak data | Low I/σ, degraded R-factors, effective resolution loss |
| Absorption error | PLAT097 family (residual density), PLAT2xx U-ratio alerts |

---

## How to add a structure

1. Place the structure files in a new subdirectory under `Good_Structures_and_data/`:
   - `<name>.hkl` — SHELXL HKLF 4 reflection file (unmerged preferred)
   - `<name>.ins` — SHELXL instruction file for the **correct model**, with `ACTA`
     and `LIST 4` (the pipeline injects `LIST 4` if absent)
   - `<published>.cif` — the deposited/published CIF (used for header metadata only)

2. Confirm the model is converged: run `shelxl <name>` once in the structure
   directory and check the `.lst` for a clean refinement.

3. Add a new entry to `structures.yaml`:

   ```yaml
   - id: your_label
     path: Good_Structures_and_data/your_label
     shelx_name: <name>           # filename stem for .hkl/.ins/.res/.cif
     published_cif: <published>.cif
     radiation: Mo                # Mo or Cu
     wavelength: 0.71073
     cell: [a, b, c, alpha, beta, gamma]  # from CELL line in .ins (skip wavelength)
     rungs:
       - {tag: "00_reference", op: reference}
       # Mo Kα — add resolution rungs:
       - {tag: "01_res_1p0", op: truncate_resolution, d_min: 1.0}
       - {tag: "02_res_1p2", op: truncate_resolution, d_min: 1.2}
       # Cu Kα — skip resolution rungs (little headroom past 0.83 Å)
       - {tag: "01_complete_88", op: reduce_completeness_random, fraction_remove: 0.12, seed: 1}
       - {tag: "02_complete_80", op: reduce_completeness_random, fraction_remove: 0.20, seed: 1}
       - {tag: "03_wedge",        op: remove_wedge, axis: l, frac_low: 0.0, frac_high: 0.20}
       - {tag: "04_wedge_lowang", op: remove_wedge, axis: l, frac_low: 0.0, frac_high: 0.30, low_angle_bias: true}
       - {tag: "05_weak",         op: simulate_weak_data, sigma_inflate: 2.0}
       - {tag: "06_absorption",   op: inject_absorption_error, mu_t: 0.8}
   ```

4. Run the pipeline and verify the reference rung is clean before trusting the degraded rungs:

   ```bash
   python run_ladder.py your_label --steps generate refine assemble validate summarize
   ```

5. Open `ladder/summary.md` and confirm the `00_reference` row has no entries in
   `unexpected_type1`. If it does, adjust the CIF merge or the published CIF choice.

---

## CHECKDEF

PLATON looks for its alert definition file (`check.def`) automatically.
If it cannot find it, the `.chk` output will be incomplete (no alert details).

To point PLATON at a specific `check.def`:

```bash
export CHECKDEF=/path/to/check.def
python run_ladder.py ...
```

Or add it to your shell profile. Copies of `check.def` exist in the PLATON
installation directory and in various crystallography program folders on this machine.

---

## Safety reminders

- Every rung directory contains a `DEGRADATION.txt` file. **Keep it.**
- These HKL files are deliberately corrupted versions of correct published
  structures. They must never be deposited, submitted, or distributed as real data.
- The model (`.ins`/`.res`) is unchanged across all rungs — it is always the
  correct published structure. Only the data changes.
- When writing teaching notes, record the original DOI/refcode and the exact
  degradation operation (copy the `op:` line from `DEGRADATION.txt`).
