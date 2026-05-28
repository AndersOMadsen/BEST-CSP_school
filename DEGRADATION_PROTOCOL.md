# Data-degradation protocol & checkCIF alert map

Companion to `degrade_data.py`. This tells you *which quantities to pick*, *what
each rung should make checkCIF say*, and *the SHELXL command-line steps*. The
alert codes below were verified against the IUCr checkCIF documentation.

---

## The governing principle (repeat to students at the reveal)

> We degraded only the **data**. The **model** — the atoms — is the correct,
> published structure throughout. So every alert you see is the validation system
> reacting to *bad data under a good model*. This is exactly the situation of a
> correct structure measured on a bad day, a bad instrument, or with restricted
> access to reciprocal space.

---

## Workflow per source structure

1. **Gather inputs:** `<name>.hkl` (unmerged, HKLF 4 — one line per observation
   with redundancy) and `<name>.ins` (the correct model). Unmerged data is what
   makes wedge removal and the absorption injection honest.
2. **Establish Rung 0 (the control).** Re-refine the correct model against the
   *untouched* data in *your* SHELXL, build the CIF+FCF, run checkCIF. This is
   your baseline so that later alerts are attributable to degradation, not to a
   software/version difference from the original deposition. **Do not skip.**
3. **Edit the `RUNGS` list** in `degrade_data.py` with quantities chosen using
   the guidance below, then run:
   ```
   python degrade_data.py <name> --cell a b c alpha beta gamma
   ```
4. **Refine each rung** (see SHELXL steps) and run checkCIF on each.
5. **Record**, per rung, the alerts that actually fired into your
   `metadata.json` teaching note — including the *level* (A/B/C), since the same
   alert at different severities is itself a teaching point.

---

## Choosing quantities (for a high-resolution, <0.8 Å source)

You have headroom, which is what makes a clean ladder possible. Principles:

**Resolution truncation.** The IUCr/"Acta" resolution limit is sin(θ)/λ = 0.6,
i.e. d ≈ 0.83 Å; checkCIF starts caring below this. So a source at, say, 0.65 Å
gives you room for a graded series. A sensible ladder: full → d_min ≈ 1.0 Å
(noticeable, still solvable comfortably) → d_min ≈ 1.2 Å (clearly degraded; the
reflections-to-parameters ratio starts to bite). Avoid going so coarse the
refinement misbehaves — past ~1.4–1.5 Å for a small organic you're teaching
"broken" rather than "degraded."

**Completeness (random).** Completeness alert thresholds are sharp: <95% → C,
<90% → B, <85% → A. So to land specific levels, target final completeness just
inside each band — e.g. remove ~12% to sit near 88% (B), ~20% to sit near 80%
(A). Check the *actual* resulting completeness in checkCIF, since removing N% of
observations is not exactly N% completeness loss after merging.

**Wedge removal.** This is your electron-diffraction / high-pressure analogue.
Two flavours, and the second is the richer lesson:
- *Plain wedge* (`low_angle_bias=False`): removes an azimuthal band uniformly →
  lowers overall completeness with a directional character.
- *Low-angle-biased wedge* (`low_angle_bias=True`): concentrates the missing
  data at low angle, producing the subtle and realistic signature where
  completeness is *worse at low resolution than high*. This is the one most
  students have never been taught to read. Start by removing ~20–30% of the
  azimuth; tune until checkCIF reports a meaningful completeness hit.

**Weak-data / noise.** `sigma_inflate=2.0` is a good first try — doubling sigmas
roughly halves I/σ and effectively amputates the high-angle data without
formally truncating it. A nice contrast rung: same *visible* resolution as the
reference, but the data are weak. Teaches that "measured to high angle" ≠
"useful to high angle."

**Absorption error.** `mu_t` controls severity; start at ~0.8 and adjust. Because
this is a teaching-grade direction-dependent transmission (not a true absorption
surface), tune it to produce *noticeable but interpretable* residual density and
ADP distortion rather than chaos. This is the rung that most needs eyeballing —
inject, refine, look at the residual density, dial `mu_t` up or down.

> General tuning rule: aim for **diagnosable but not catastrophic**. A rung that
> throws an A-alert you can *explain* beats one that won't refine.

---

## What each rung should make checkCIF say (verified alert map)

Put the relevant rows into each rung's teaching note. Severities depend on how
hard you push; the *which alerts* is reliable, the *level* you confirm from the
actual run.

| Rung / operation | Expected checkCIF alerts | Where the student looks |
|---|---|---|
| Resolution truncation | **PLAT???** reflections-to-parameters ratio (RRTP) → ALERT C (<10) / B (<8) / A (<6) for centrosymmetric; resolution-limit alert when sin(θ)/λ < 0.6 ("Acta limit"); degraded bond-precision (PLAT341 family, low C–C precision); ADP-determination alerts | **Structure-factor report + checkCIF numbers**, NOT Mercury for the ratio/resolution part. ADP effects visible in Mercury (ellipsoids grow / less well-determined). |
| Completeness (random) | **REFLT03** family: <95% → C, <90% → B, <85% → A; **PLAT022** (ratio unique/expected reflns too low); **PLAT029** (low `_diffrn_measured_fraction_theta_full`) | checkCIF output + structure-factor report. Not visible in Mercury. |
| Wedge (plain) | Same completeness alerts as above (REFLT03 / PLAT022 / PLAT029), plus possible "expected hkl max differ from CIF values" general alert from the missing directions | checkCIF output; the FCF missing-reflection listing shows the gap. |
| Wedge (low-angle biased) | The above **plus** the *theta_full < theta_max* signature — completeness worse at low angle than high (PLATON reports their ratio when <1.0); the FCF check lists missing low-angle reflections with their expected intensities | structure-factor report / FCF listing. This is the subtle one — teach them to read theta_full vs theta_max. |
| Weak data / noise | Low I/σ, degraded R-factors, effective resolution alerts; reflections-to-parameters effects if many reflns drop below the σ threshold | structure-factor report (I/σ, R-factors). |
| Absorption error | Spurious **residual electron density** (Q-peak / PLAT097 family — highest residual density too large), inflated/anisotropic **ADPs** (PLAT2xx U-ratio alerts), possibly Hirshfeld rigid-bond (PLAT230 family) | **Residual density: structure-factor report / checkCIF, NOT Mercury.** ADP anisotropy: Mercury ellipsoids. This rung is the cleanest "you can't see the cause in the viewer" lesson. |

> Verify exact PLAT numbers against your bundled `checkcif_alerts.json` and the
> actual reports — the reflections-to-parameters alert in particular is issued by
> a PLATON test whose exact code you should confirm from the run rather than from
> this table. The *families* and *trigger conditions* above are correct; pin the
> precise code from your own output.

This table maps directly onto the `evidence_pointers.json` in the app brief: the
"where the student looks" column is exactly the evidence-pointer text, and it
honours the rule that residual-density and completeness alerts route to the
numbers, not to Mercury.

---

## SHELXL command-line steps (per rung)

In each `rung_*/` directory you have `<name>.hkl` (degraded) and `<name>.ins`
(correct model, with `LIST 4` ensured by the script). Then:

```bash
# 1. Refine the correct model against the degraded data
shelxl <name>            # reads <name>.ins + <name>.hkl -> <name>.res, <name>.fcf, <name>.lst

# 2. The .fcf is the LIST 4 reflection file checkCIF wants for full validation.
#    Build a CIF for checkCIF. If you refine via Olex2 you get the CIF directly;
#    on the command line, generate/merge a CIF (e.g. with your usual tool) that
#    includes the cell, symmetry, refinement results and the embedded .res.

# 3. Run checkCIF: upload BOTH <name>.cif and <name>.fcf at
#    https://checkcif.iucr.org/  (both files = full reflection-data alerts)
```

Notes:
- `LIST 4` produces the SHELXL-style Fo/Fc FCF that is required for full FCF
  validation in checkCIF — the script injects it if absent.
- Keep the model fixed across rungs: do **not** re-optimise the model to "fix"
  the degraded data — the whole point is to watch a *correct* model react.
  (You may need to allow the refinement to converge, but don't change the atom
  list, the disorder model, or restraints between rungs.)

---

## Labelling & safety (do not skip)

Every degraded artefact must be unmistakably marked as such, because a degraded
teaching CIF escaping into the wild and being mistaken for a real determination
is a genuine contamination risk (cf. the Acta E fraud history).

- The script writes a `DEGRADATION.txt` stamp in every rung. Keep it.
- Add a comment block at the top of each teaching CIF:
  `# TEACHING ARTEFACT — data deliberately degraded from <DOI/refcode>. NOT the
  published structure. Model atoms unchanged; data degraded for instruction.`
- In `metadata.json`, use a distinct `source_route`, e.g. `"synthetic-degraded"`,
  and record the original DOI/refcode and the exact degradation op (copy the
  `DEGRADATION.txt` line) in the provenance fields.
- The hidden `teaching_note` should state plainly what was done and what the
  correct structure is, so the reveal is unambiguous.
