# Amendment to MODEL_ERROR_BRIEF.md — add rung MA (missing atoms / unmodelled solvent)

## A.0 What this amendment does

`MODEL_ERROR_BRIEF.md` defines two model-error rungs: MS (missed symmetry) and
WA (wrong atom assignment). This amendment adds a third sibling rung in the same
family — **rung MA (missing atoms)** — and integrates it via the same
orchestrator, convergence gate, gemmi CIF assembly, and provenance machinery.
Inherit everything from `MODEL_ERROR_BRIEF.md` (especially §0 — model changes,
data untouched) and add only what is in this amendment.

For the course we instantiate rung MA as the canonical case: **unmodelled
solvent water in a hydrate structure.** The mechanism generalises (you could
later omit a disordered minor component, or hydrogens that should be modelled),
but the implementation here targets the solvent-omission case.

## A.1 Pedagogical framing — this is NOT "we deleted a water"

The teaching frame is **"this is what an *unmodelled* solvent looks like in
checkCIF."** The student's job is to read the void + residual-density + formula
evidence and recognise "there is solvent here that the refiner missed." That is
the failure mode that occurs in the wild — diffuse density the refiner couldn't
make sense of and ignored — and it is the lesson worth teaching. The deletion
is the construction method, not the lesson.

This matters for the `teaching_note` and the reveal. The reveal is **not** "we
deleted the water"; it is "the void PLATON found is real — here is the water
that lives in it; here is the published structure with it modelled correctly."
Write the teaching note in those terms.

## A.2 Host structure (fixed for this rung)

- Code name **`jp2026`** — a hydrate whose published reference has already been
  confirmed to validate cleanly (no spurious voids, no spurious high residual
  density). This is the precondition for the rung; do not substitute another
  hydrate without re-confirming clean reference validation.

## A.3 Operation

Given `jp2026` and a chosen water (or set of waters):

1. **Modify the model only.** In the `.ins`: remove the water O atom(s) and any
   associated H atoms; remove any restraints/constraints that reference those
   labels (DFIX/DANG/SADI/EADP/PART blocks etc.). Adjust `SUMP`/`FVAR`/`SOF`
   references only as necessary to keep the file syntactically valid. Do NOT
   move or modify any non-water atom.
2. **Leave the `.hkl` untouched.** Same data discipline as MS / WA.
3. **Keep the chemical-formula and density fields carrying the water.** Specifically:
   - In the assembled CIF, **preserve `_chemical_formula_sum`,
     `_chemical_formula_moiety`, `_chemical_formula_weight`, and the calculated
     density fields as they appear in the published CIF** — i.e. including
     the water contribution.
   - The mismatch between the modelled atoms and the declared formula is part
     of the diagnostic. The CIF-consistency / Type_1 alerts that arise from
     this mismatch are intended, not a bug to be silenced.
4. **Re-refine.** Run SHELXL on the modified `.ins` against the untouched `.hkl`
   to convergence. This lets surrounding atoms relax slightly toward the empty
   space, producing a realistic "frozen post-failure" state — refiners in the
   wild who missed a water have *already* completed their refinement.
5. **Apply the same convergence / sanity gate** as for MS / WA (converged?
   bounded R-factors? positive-definite ADPs?). A water deletion is usually
   mild and stable, but the gate still applies.
6. **Assemble the CIF** via the existing gemmi pipeline. The formula/density
   preservation is the only deviation from the standard merge — verify after
   assembly that those four fields still carry the water-containing values from
   the published CIF, and that the modelled atom list does **not** contain the
   deleted water.
7. **Validate** with `platon -u` as for the other rungs. Keep both `.chk` and
   `.ckf`.

## A.4 Per-structure config (extend `structures.yaml` for `jp2026`)

```yaml
ma_rung:
  enabled: true
  delete_atoms:
    - "O1W"            # the water oxygen label, instructor fills in
    - "H1WA"           # associated H atoms; instructor fills in actual labels
    - "H1WB"
  preserve_formula_fields: true   # keep formula/density carrying the water
  note: "Hydrate water deleted from model; data and chemical formula unchanged"
```

The atom labels are placeholders — the instructor fills the real labels from
`jp2026`'s `.ins`.

## A.5 Expected alerts (extend the protocol table with a fourth model-error row)

| Alert family | Code(s) | What fires it | Severity expectation |
|---|---|---|---|
| Residual electron density | PLAT097 family (Type_2; largest residual density too large) | The water's electrons are still in the data but not in the model; they pile up as a difference-density peak where the water sat. | Often **ALERT A** — this is the headline. |
| Solvent-accessible voids | **PLAT601** family (and related void/cavity tests) | PLATON detects empty space large enough to hold a small molecule. | A or B depending on void size. |
| Formula / density consistency | Type_1 family — `_chemical_formula_sum` vs modelled atoms; calculated density vs reported | The CIF declares atoms (including water) the model doesn't contain; modelled-vs-declared mismatch. | Usually B. |
| Possibly: SQUEEZE-related notes | If the published structure used or didn't use SQUEEZE, PLATON may comment. | Side-channel signal. | Variable. |

> Pin the **exact** PLAT codes (especially the residual-density code and the
> void test code) from the actual `jp2026` reference and rung-MA runs — the
> *families* and *what fires them* are reliable; the precise codes you confirm
> from the run.

**Evidence pointer for `evidence_pointers.json`:** all of these alerts route to
**the checkCIF output, the structure-factor report, and a PLATON void map** —
**NOT** to Mercury. This is exactly the "you can't see this in the viewer"
lesson, and the rung must teach that residual density and voids are number-and-
report diagnostics, not ball-and-stick ones. The void map is its own
visualisation but it lives inside PLATON, not Mercury.

## A.6 Provenance & labelling

Same machinery as MS / WA. Write a `MODEL_MODIFICATION.txt` provenance stamp in
the rung directory recording the deleted atom labels and the source DOI/refcode
for `jp2026`. CIF top-comment block:

```
# TEACHING ARTEFACT — model deliberately modified from <DOI/refcode for jp2026>.
# NOT the published structure. Data and chemical formula unchanged;
# solvent atoms removed from the modelled atom list for instruction.
```

In the app's `metadata.json`, use a new `source_route` value
**`"synthetic-missing-atoms"`**, distinct from `synthetic-degraded`,
`synthetic-wrong-symmetry`, and `synthetic-wrong-atom`.

## A.7 Guardrails

In addition to the guardrails of `MODEL_ERROR_BRIEF.md` §7:

- Do **not** modify `_chemical_formula_sum`, `_chemical_formula_moiety`,
  `_chemical_formula_weight`, or the calculated density fields. They must carry
  the published, water-containing values. The orchestrator must verify this in
  the assembled CIF before running validation.
- Do **not** touch the `.hkl`.
- Do **not** move or modify any non-water atom, even slightly. Only deletion
  and consequent restraint/constraint cleanup is permitted.
- Do **not** silently suppress formula-mismatch alerts in the summary table —
  they are intended diagnostics for this rung. The "alerts not attributable to
  the intended modification" column should mark them as **expected**, not
  unexpected.

## A.8 Deliverables

- A new rung generator (e.g. `generate_ma_rung.py`) callable from the existing
  orchestrator, with the contract from `MODEL_ERROR_BRIEF.md` §3 (modified
  `.ins`, copied original `.hkl`).
- `structures.yaml` extended with an `ma_rung` block under `jp2026`.
- Extended protocol table row (§A.5 above) added to the protocol document
  alongside the MS and WA rows.
- Summary table now has up to one additional row per structure (only for those
  with `ma_rung.enabled: true`), with the same stats/alerts/expected-flag
  columns as the other rungs.
- README addition: the §A.1 framing, the formula-preservation rule, and the
  evidence-pointer note (not Mercury — PLATON void map + checkCIF + SF report).
