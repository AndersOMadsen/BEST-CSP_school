# Claude Code brief — model-error rungs (missed symmetry + wrong atom assignment)

## 0. READ FIRST — this brief INVERTS the principle of the previous ones

The previous briefs (`degrade_data.py`, the automation pipeline) were built on a
strict rule: **degrade the data, never touch the model.** That rule was
load-bearing for everything you have done so far.

**This brief is different. Here we deliberately produce a WRONG MODEL refined
against UNTOUCHED, ORIGINAL data.** The reversal is intentional and is the whole
point of these rungs. Do not apply the previous discipline to this job, and do
not regard these rungs as variants of the data-degradation ladder. They are a
separate teaching family.

The pedagogical principle for this brief:
> Degrade the **model**, keep the **data** pristine. The lesson is that *the
> model itself can be wrong* in ways that *the data will not shout about*, and
> that PLATON catches this specifically through the missed-symmetry and
> Hirshfeld-rigid-bond families of tests.

## 1. What you are building

Two new rungs, additive to the existing ladder produced by the data-degradation
pipeline:

- **Rung MS — missed symmetry.** A correct higher-symmetry structure refined in
  a deliberately too-low space group (typically the correct space group's
  subgroup with the inversion centre or a key symmetry element removed).
  Expected diagnostic: **ADDSYM family** (PLAT111 / PLAT112 / **PLAT113** — the
  headline "Possible Pseudo/New Space-Group" alert).
- **Rung WA — wrong atom assignment.** A correct structure in which one or two
  atoms have their element type swapped (e.g. C↔N, O↔F) at chemically/symmetry-
  significant positions. Expected diagnostics: **Hirshfeld rigid-bond test
  (PLAT230 family)** when the swap distorts bond geometry, and ADDSYM (which by
  design treats atom types as EQUAL for asymmetric units <250 atoms, specifically
  to catch misassigned atoms) when the swap breaks symmetry the structure
  otherwise has.

These rungs do **not** use `degrade_data.py` and do **not** touch the HKL files.
They produce a modified `.ins` (model) and reuse the structure's original,
untouched `.hkl`.

## 2. Existing assets you must treat as fixed

- The data-degradation pipeline (`degrade_data.py`, the orchestrator,
  `structures.yaml`, the gemmi CIF-assembly module, the PLATON parser, the
  summary-table format) — REUSE these unchanged for the refine→assemble→validate
  steps. The only new thing is *how a rung is generated*.
- The per-structure published Acta E CIFs and their command-line SHELXL inputs.
- `DEGRADATION_PROTOCOL.md` — extend it (do not rewrite) with the new rungs;
  the protocol's "what the rung should make checkCIF say" table gains two rows.
- `shelxl` and `platon` at `/usr/local/bin`; `gemmi` and `numpy` in Python.

## 3. Integration with the existing pipeline

Add two new rung *generators* alongside the existing data-degradation ones. The
generator's contract is: given a structure's `.ins` and `.hkl` (and its
published CIF for metadata), produce a rung directory containing the
**modified** `.ins` and a **copy of the original** `.hkl`. From that point on
the existing pipeline (SHELXL → gemmi CIF assembly → `platon -u`) runs
unchanged.

Extend the per-structure config (`structures.yaml`) so each structure can opt
into MS and/or WA rungs with the specific parameters they need (which space
group to drop to, which atoms to swap). These are **per-structure choices** the
instructor makes — do not auto-pick them.

## 4. Rung MS — missed symmetry (generator spec)

### 4.1 Operation
Given a structure in some space group G with an extra symmetry element (most
commonly an inversion centre making G centrosymmetric), produce a new `.ins`
that refines the same atoms in a chosen **subgroup G'** of G — typically G with
the inversion removed (e.g. P2₁/c → P2₁, C2/c → Cc, P-1 → P1, Pnma → Pna2₁).

This means:
- Change `SPGR` / the symmetry instructions in `.ins` to the subgroup.
- Expand the atom list as required by the subgroup (atoms previously related by
  the removed symmetry become independent — typically this doubles the
  asymmetric unit; you must generate the symmetry-expanded coordinates).
- Update Z / Z' fields consistently.
- Re-couple any constraints/restraints sensibly for the larger asymmetric unit.

This is non-trivial to do robustly across all space groups. Use **gemmi**'s
symmetry tools (`gemmi.SpaceGroup`, generators, asymmetric-unit expansion) to
perform the expansion deterministically. **Verify the gemmi calls against the
installed gemmi version at build time** rather than asserting signatures.

### 4.2 Per-structure config (in `structures.yaml`)
For each structure opting into rung MS:
```yaml
ms_rung:
  enabled: true
  drop_to_subgroup: "P-1"          # or "P21", "Cc", etc.
  shift_to_origin: [0.0, 0.0, 0.0] # if a non-standard origin is needed
  note: "Original P21/c -> P-1 by removing inversion centre"
```

### 4.3 Stability warning — propagate this into the README and the rung's note
A centrosymmetric structure refined in a non-centrosymmetric subgroup
"generally results in poor geometry due to (near) singularity of the
least-squares normal matrix" (IUCr, PLATON paper). The least-squares may
misbehave to the point of producing meaningless ADPs or failing to converge.

**Implication for the rung generator:** after SHELXL refinement, the orchestrator
must check basic sanity (did it converge? are R-factors finite and bounded? are
the ADPs positive-definite?) and **flag the rung as catastrophic-not-diagnosable
if these fail**, so the instructor knows to either choose a different subgroup,
shift the origin, or pick a different source structure. This is the same
"diagnosable but not catastrophic" gate from the data-degradation work, applied
to model construction. Do not silently produce a broken rung.

### 4.4 Expected alerts (extend the protocol table)
- **PLAT113 (Type_2)** — "ADDSYM Suggests Possible Pseudo/New Space-Group". The
  headline alert.
- **PLAT111 / PLAT112 (Type_2)** — additional inversion centre / additional
  symmetry elements.
- Likely also: degraded bond-precision and ADP alerts as a secondary
  consequence of the poorly-conditioned refinement.

**Evidence pointer (for the app's `evidence_pointers.json`):** ADDSYM alerts
are investigated by **running PLATON/ADDSYM** on the structure and inspecting
the proposed transformation — NOT in Mercury (which shows you geometry but
won't tell you a symmetry element is missing). Update the evidence overlay
accordingly.

## 5. Rung WA — wrong atom assignment (generator spec)

### 5.1 Operation
Given a structure, swap the element type of one or two atoms at instructor-
specified atom labels. Common choices: C↔N (similar number of electrons,
diagnostic comes from bond length and Hirshfeld test), O↔F, or for the
symmetry-diagnostic version, swap atoms at sites that *would* be related by an
unrecognised symmetry element (this triggers the ADDSYM EQUAL-atoms detection
discussed below).

This means:
- In the `.ins`: change the `SFAC` ordering if needed so the new element is
  present, change the atom-line element-type code, do not move coordinates.
- Leave the `.hkl` untouched.

### 5.2 Per-structure config
```yaml
wa_rung:
  enabled: true
  swaps:
    - atom: "N3"
      from_element: "N"
      to_element: "C"
    - atom: "C8"
      from_element: "C"
      to_element: "N"
  note: "C/N swap at a pyrimidine-ring position"
```

### 5.3 The two diagnostic mechanisms — be explicit in the README about both
- **Hirshfeld rigid-bond test (PLAT230 family).** When the misassignment
  distorts the apparent bond geometry, the Hirshfeld test on bonded atoms'
  ADP components flags it as non-physical.
- **ADDSYM with EQUAL-atom-types.** For asymmetric units <250 atoms, PLATON's
  ADDSYM treats atom types as equal during the symmetry search precisely to
  catch misassigned atoms — so swapping a C↔N at a position that *would* be
  symmetry-equivalent under higher symmetry produces an ADDSYM hit. This is
  the cleanest version of the rung because it ties the WA and MS rungs into
  one coherent diagnostic story.

The instructor should prefer the latter variant when possible — the structure
becomes a vehicle for teaching *both* alert families with one swap.

### 5.4 Stability warning
A C↔N swap is usually stable; an O↔F or heavier swap is more aggressive and may
produce large residuals or fail to converge. Apply the same convergence /
sanity gate as for rung MS.

### 5.5 Expected alerts (extend the protocol table)
- **PLAT230 (Hirshfeld test) family** — when bond geometry is distorted.
- **PLAT113 / PLAT111 / PLAT112** — when the swap breaks pseudo-symmetry the
  structure otherwise has (ADDSYM EQUAL mode).
- Possibly elevated residual density near the swapped atom (a wrong scattering
  factor produces a difference-density signature).

**Evidence pointer:** Hirshfeld alerts → look at the flagged bond in Mercury
and check whether the bond length and the displacement of the two atoms along
the bond are physically reasonable. ADDSYM hits → run PLATON/ADDSYM. Residual
density near the atom → checkCIF / structure-factor report.

## 6. Provenance & labelling (do not skip)

Every rung MS / WA artefact must be marked as a deliberate teaching artefact,
the same as the degraded-data rungs:
- Write a `MODEL_MODIFICATION.txt` provenance stamp in each rung dir, with the
  exact modification (subgroup chosen / swaps performed), original space group
  / atom assignments, and the source DOI/refcode.
- The CIF must carry a top-comment block: `# TEACHING ARTEFACT — model
  deliberately modified from <DOI/refcode>. NOT the published structure. Data
  unchanged; model altered for instruction.`
- In the app's `metadata.json`, use a distinct `source_route`:
  `"synthetic-wrong-symmetry"` or `"synthetic-wrong-atom"`, separate from
  `"synthetic-degraded"`. The teaching note states plainly what was done.

## 7. Guardrails — do NOT do these

- Do **not** touch the `.hkl` for these rungs. Data is pristine; only the model
  changes.
- Do **not** apply the data-degradation discipline ("never change the model")
  here — this brief explicitly reverses that rule for these rungs only. The
  data-degradation pipeline's rule is unchanged for its own rungs.
- Do **not** auto-pick the subgroup or the atom swaps. The instructor specifies
  both in `structures.yaml`. Auto-picking lands either in catastrophic
  refinements or in undiagnosable subtle ones.
- Do **not** silently emit broken rungs. If SHELXL fails to converge or the
  refinement produces obviously meaningless results (non-positive-definite ADPs,
  runaway R-factors, etc.), mark the rung as catastrophic in the summary and
  emit a clear instructor-facing message rather than passing junk down the
  pipeline.
- Do **not** validate against the published CIF as if it were the result. As
  before, the published CIF is metadata-source and ground-truth-for-reveal only.
- Do **not** submit anything to the IUCr checkCIF web service. Validation is
  local via `platon -u` only.

## 8. Deliverables

- Two new rung generators (e.g. `generate_ms_rung.py`, `generate_wa_rung.py`)
  callable from the existing orchestrator, with the contract described in §3.
- `structures.yaml` extended with `ms_rung` and `wa_rung` blocks per structure
  (stubbed and commented; instructor fills the parameters).
- Convergence / sanity gate in the orchestrator that flags catastrophic rungs.
- Extended `DEGRADATION_PROTOCOL.md` (or a new `MODEL_ERROR_PROTOCOL.md` next to
  it) with the two new rows in the alert table and the evidence pointers.
- The summary table per structure now has two extra rows (one per new rung)
  with their stats and alerts, and the "alerts not attributable to the intended
  modification" flag column behaves the same way as before.
- README updates: the principle reversal in §0 stated explicitly, the stability
  warnings from §4.3 and §5.4, and how to choose subgroups / swaps sensibly.
