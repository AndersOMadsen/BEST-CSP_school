# Model-error rung protocol

Companion to `DEGRADATION_PROTOCOL.md`.  That document covers data-degradation
rungs (wrong data, correct model).  This document covers the two model-error
rungs (correct data, wrong model).

## The governing principle (repeat to students at the reveal)

> We left the **data** completely untouched — every reflection, every intensity,
> every sigma, exactly as measured.  What we changed is the **model**: either
> the space group (rung MS) or the element assignment (rung WA).  The lesson is
> that the *model itself can be wrong* in ways the data will not shout about,
> and that PLATON catches this specifically through its symmetry-search and
> rigid-bond-test families.

---

## Rung MS — missed symmetry

### What was done

The correct space group was replaced by a subgroup, most commonly by removing
the inversion centre (e.g. P2₁/c → P2₁, C2/c → Cc, P-1 → P1).  The
asymmetric unit was doubled by generating inverted copies of all atoms.  The
generator negates the SHELXL LATT value: `LATT N` (centrosymmetric) →
`LATT -N` (non-centrosymmetric).

### Stability warning — tell students before the reveal

A centrosymmetric structure refined in a non-centrosymmetric subgroup has a
near-singular least-squares normal matrix (the free variables are not uniquely
determined by the data).  SHELXL may produce non-positive-definite ADPs, fail
to converge, or produce inflated R-factors.  The pipeline sanity gate checks
for these and writes `CATASTROPHIC.txt` if they occur.

If the rung is marked catastrophic: try a different origin shift
(`shift_to_origin` in `structures.yaml`), or choose a different source
structure, before using it for teaching.

### What PLATON / checkCIF should say

| Alert | Level | Description |
|---|---|---|
| PLAT113 | Type_2, usually B or A | "ADDSYM Suggests Possible Pseudo/New Space-Group" — the headline alert |
| PLAT111 | Type_2 | Additional inversion centre found by ADDSYM |
| PLAT112 | Type_2 | Additional symmetry element found by ADDSYM |
| PLAT230 family | Type_2 | Hirshfeld rigid-bond test violations, as a secondary consequence of poorly-conditioned ADPs |
| Elevated R / GooF | (stats) | Refinement did not converge to the correct geometry |

### Where the student looks

The ADDSYM alerts are in the `.chk` alert listing.  The underlying evidence is
not in Mercury (which shows you geometry but cannot diagnose a missing
symmetry element).  Students should:
1. Note the PLAT113 alert in the PLATON report.
2. Run PLATON/ADDSYM on the structure and inspect the proposed transformation
   and the suggested new space group.
3. Apply the suggested transformation and re-refine to confirm.

---

## Rung WA — wrong atom assignment

### What was done

The element type of one or two atoms was swapped in the `.ins` (e.g. C→N,
N→C) while the `.hkl` was left completely unchanged.  The SFAC line was
updated if a new element was introduced.  Coordinates are unchanged.

### Diagnostic mechanisms (both may fire; explain both to students)

**1. Hirshfeld rigid-bond test (PLAT230 family).**
When the wrong scattering factor is used, the refined bond lengths will be
displaced from chemically reasonable values.  The Hirshfeld test flags bonds
where the components of ADP along the bond direction differ significantly
between the two atoms — a fingerprint of a misassigned atom trying to
compensate for the wrong X-ray scattering factor.

**2. ADDSYM EQUAL-atoms mode (PLAT113 / PLAT111).**
For asymmetric units < 250 atoms, PLATON's ADDSYM deliberately treats all
atom types as EQUAL during the symmetry search.  This means: if you swap C for
N at a site that would be related by an unrecognised symmetry element to
another site, ADDSYM will find that symmetry element.  This ties rung WA and
rung MS into a single coherent diagnostic story — both can produce ADDSYM hits
via different mechanisms.

The ADDSYM-EQUAL version is the pedagogically richer choice because it teaches
students that the same PLATON alert (PLAT113) can arise from two different
problems (missing symmetry from a wrong space group, or a misassigned atom
that breaks pseudo-symmetry).

### What PLATON / checkCIF should say

| Alert | Level | Description |
|---|---|---|
| PLAT230 family | Type_2, A/B/C | Hirshfeld rigid-bond test — ADP components along bond are non-physical |
| PLAT971 / PLAT977 | Type_2 | Elevated residual density near the misassigned atom |
| PLAT113 / PLAT111 | Type_2 | ADDSYM may flag missed symmetry if the swap breaks pseudo-symmetry |

### Where the student looks

- **Hirshfeld alert:** look at the flagged bond in Mercury (or in the PLATON
  structure list).  Check: is the bond length chemically reasonable?  Do the
  ellipsoids along the bond look physically sensible?
- **Residual density:** checkCIF / structure-factor report.  A wrong scattering
  factor leaves difference density on or near the atom.
- **ADDSYM hit:** run PLATON/ADDSYM.  Note: NOT visible in Mercury.

---

## Summary table extension

The rung-level summary (from `run_ladder.py --steps summarize`) includes
model-error rungs alongside data-degradation rungs.  The `catastrophic` column
flags rungs where the sanity gate fired.  The `new_alert_codes` column lists
PLATON alert codes that appeared in the model-error rung but not in the
reference rung — these are the intended diagnostic signals.

Expected new codes for a working MS rung: 111, 112, 113 (ADDSYM family).
Expected new codes for a working WA rung: 230-family (Hirshfeld), 971/977
(residual density), possibly 113 (ADDSYM if pseudo-symmetry broken).

---

## How to choose subgroup / swaps (instructor guidance)

### For rung MS

1. Confirm the source structure is centrosymmetric (LATT > 0 in the `.ins`).
2. The simplest drop is always P-1 → P1 (just negate LATT 1 → -1, no SYMM
   changes needed).  Try this first.
3. For monoclinic (P2₁/c, P2₁/n, C2/c): drop to the non-centrosymmetric
   variant (P2₁, Cc).  The SYMM cards remain unchanged; only LATT is negated.
4. Run the pipeline and check the `.lst` for convergence.  If `CATASTROPHIC.txt`
   appears, try a different structure.

### For rung WA

1. Choose a C/N pair in the structure (a ring or chain position where C and N
   are chemically interchangeable in appearance).
2. Prefer a swap at a site that would be symmetry-equivalent under the Laue
   group if all atom types were made equal — this triggers ADDSYM as well as
   the Hirshfeld test.
3. Avoid O↔F or heavier swaps as a first choice: the electron-count difference
   is larger and the refinement may diverge.
4. Fill in `atom:` and `from_element:`/`to_element:` in `structures.yaml`,
   set `enabled: true`, and re-run the pipeline.
