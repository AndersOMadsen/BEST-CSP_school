#!/usr/bin/env python3
"""
degrade_data.py  —  Reproducible data degradation for crystallography teaching
==============================================================================

PURPOSE
    Take a HIGH-QUALITY, CORRECT structure (model + unmerged reduced data) and
    produce a "ladder" of versions in which ONLY THE DATA is degraded, never the
    atomic model. Re-refining the identical correct model against each degraded
    HKL with SHELXL gives an honest picture of how validation signals decay.

    This is a teaching tool. Every output is a DELIBERATELY DAMAGED version of a
    correct, published structure. See the labelling requirement at the bottom.

GOVERNING PRINCIPLE
    Degrade the DATA, re-refine the CORRECT model, never touch the atoms.
    Every rung uses the identical published .ins/.res model; only the .hkl
    changes. This keeps ground truth pristine and isolates the variable.

INPUT  (per source structure, you provide)
    <name>.hkl   SHELX HKLF 4 reflection file. UNMERGED is strongly preferred
                 (one line per observation, with redundancy) so that wedge
                 removal and completeness reduction are honest. Columns:
                 h k l Fo^2 sigma(Fo^2)  [batch].
    <name>.ins   SHELXL instruction file for the CORRECT model, matching the
                 published structure. Must contain (or we will inject) LIST 4
                 so checkCIF can do full FCF reflection-data validation.

OUTPUT (per rung)
    rung_<tag>/<name>.hkl   degraded reflections
    rung_<tag>/<name>.ins   copy of the correct model (unchanged atoms)
    ...then YOU run:  shelxl <name>   in each rung dir, then build the CIF+FCF.

WHAT THIS SCRIPT DOES / DOES NOT DO
    DOES:  resolution truncation, completeness reduction by random fraction,
           completeness reduction by removing an angular WEDGE (low-angle-biased
           option for the theta_full < theta_max signature), light-data / noise
           simulation, and an honest absorption-error injection that REQUIRES
           unmerged data + per-reflection direction info.
    DOES NOT: run SHELXL for you, or write the CIF. Those steps are in the
           PROTOCOL section of the companion .md so you stay in control of the
           refinement and can inspect each rung.

UNITS
    Resolution cutoffs are given as d_min in Angstrom (more intuitive than
    sin(theta)/lambda). Conversion: d = 1 / (2 * sin(theta)/lambda), i.e.
    s = sin(theta)/lambda = 1/(2 d). The IUCr "Acta" resolution limit is
    s = 0.6 (d ~ 0.833 A); checkCIF starts caring about resolution below this.

DEPENDENCIES
    numpy only. (pip install numpy)
"""

from __future__ import annotations
import argparse
import shutil
from pathlib import Path
import numpy as np


# ----------------------------------------------------------------------------
# HKL I/O  (SHELX HKLF 4 fixed format: 3I4, 2F8.2, optionally I4 batch)
# ----------------------------------------------------------------------------

def read_hklf4(path: Path) -> np.ndarray:
    """Read a SHELX HKLF 4 file into a structured array.

    Returns rows with fields h,k,l,F2,sig,batch. Stops at the terminating
    0 0 0 line if present. Batch defaults to 1 when absent.
    """
    rows = []
    with open(path) as fh:
        for line in fh:
            if len(line.rstrip("\n")) < 28:
                continue  # not a data line
            try:
                h = int(line[0:4]); k = int(line[4:8]); l = int(line[8:12])
                f2 = float(line[12:20]); sig = float(line[20:28])
            except ValueError:
                continue
            if h == 0 and k == 0 and l == 0:
                break  # HKLF terminator
            batch = 1
            if len(line) >= 32 and line[28:32].strip():
                try:
                    batch = int(line[28:32])
                except ValueError:
                    batch = 1
            rows.append((h, k, l, f2, sig, batch))
    dt = np.dtype([("h", "i4"), ("k", "i4"), ("l", "i4"),
                   ("F2", "f8"), ("sig", "f8"), ("batch", "i4")])
    return np.array(rows, dtype=dt)


def write_hklf4(path: Path, data: np.ndarray) -> None:
    """Write a structured array back to SHELX HKLF 4 fixed format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        for r in data:
            fh.write("%4d%4d%4d%8.2f%8.2f%4d\n" %
                     (r["h"], r["k"], r["l"], r["F2"], r["sig"], r["batch"]))
        fh.write("   0   0   0    0.00    0.00\n")  # terminator


# ----------------------------------------------------------------------------
# Geometry: resolution and reciprocal-space direction
# ----------------------------------------------------------------------------

def reciprocal_metric(cell: tuple[float, float, float, float, float, float]) -> np.ndarray:
    """Return the reciprocal metric tensor G* from direct cell parameters
    (a,b,c,alpha,beta,gamma) with angles in degrees. d* = sqrt(h . G* . h)."""
    a, b, c, al, be, ga = cell
    al, be, ga = np.radians([al, be, ga])
    ca, cb, cg = np.cos([al, be, ga])
    sa, sb, sg = np.sin([al, be, ga])
    V = a * b * c * np.sqrt(
        1 - ca**2 - cb**2 - cg**2 + 2 * ca * cb * cg)
    # reciprocal cell
    asx = b * c * sa / V
    bsx = a * c * sb / V
    csx = a * b * sg / V
    cas = (cb * cg - ca) / (sb * sg)
    cbs = (ca * cg - cb) / (sa * sg)
    cgs = (ca * cb - cg) / (sa * sb)
    G = np.array([
        [asx*asx,           asx*bsx*cgs,      asx*csx*cbs],
        [asx*bsx*cgs,       bsx*bsx,          bsx*csx*cas],
        [asx*csx*cbs,       bsx*csx*cas,      csx*csx],
    ])
    return G


def d_spacing(data: np.ndarray, G: np.ndarray) -> np.ndarray:
    """d-spacing in Angstrom for each reflection."""
    hkl = np.stack([data["h"], data["k"], data["l"]], axis=1).astype(float)
    dstar2 = np.einsum("ij,jk,ik->i", hkl, G, hkl)
    dstar2 = np.maximum(dstar2, 1e-12)
    return 1.0 / np.sqrt(dstar2)


def s_value(data: np.ndarray, G: np.ndarray) -> np.ndarray:
    """sin(theta)/lambda for each reflection = 1/(2d)."""
    return 1.0 / (2.0 * d_spacing(data, G))


# ----------------------------------------------------------------------------
# Degradation operations  (each returns a NEW degraded array; model untouched)
# ----------------------------------------------------------------------------

def truncate_resolution(data, G, d_min: float):
    """Keep only reflections with d >= d_min (i.e. remove the highest-angle data).
    Teaches: effective resolution drop, reflections/parameter ratio collapse
    (checkCIF PLATON RRTP -> ALERT C/B/A), loss of ADP precision."""
    d = d_spacing(data, G)
    keep = d >= d_min
    return data[keep], f"resolution truncated to d_min = {d_min:.2f} A " \
                        f"({keep.sum()}/{len(data)} reflns kept)"


def reduce_completeness_random(data, fraction_remove: float, seed: int = 0):
    """Randomly remove a fraction of reflections (uniform in reciprocal space).
    Teaches: overall completeness drop (REFLT03 / PLAT022 / PLAT029),
    level set by final completeness (<95% C, <90% B, <85% A)."""
    rng = np.random.default_rng(seed)
    n = len(data)
    mask = rng.random(n) >= fraction_remove
    return data[mask], f"random completeness reduction: removed " \
                       f"{(~mask).sum()}/{n} reflns (~{fraction_remove*100:.0f}%)"


def reduce_completeness_unique(data, fraction_remove: float, seed: int = 0,
                               space_group: str | None = None):
    """Remove a fraction of UNIQUE reflections from unmerged data.

    Unlike reduce_completeness_random (which removes individual observations and
    barely moves completeness when multiplicity is high), this function groups
    all observations by their Laue-symmetry-reduced hkl and removes EVERY
    observation belonging to the selected unique reflections.

    space_group: H-M name recognised by gemmi (e.g. 'P 21/c', 'C 2/c',
        'P 21 21 21').  When provided, full Laue group symmetry is applied so
        that fraction_remove accurately targets the desired completeness drop.
        When None, falls back to Friedel-pair-only grouping (exact for triclinic
        P-1, but under-removes for higher-symmetry space groups).

    Canonical key: max of all Laue-equivalent hkl tuples (lexicographic) so
    that each unique reflection maps to a single representative.

    Teaches: overall completeness drop (REFLT03 / PLAT022 / PLAT029),
    level set by final completeness (<95% C, <90% B, <85% A).
    Use this in place of reduce_completeness_random for unmerged data."""
    import gemmi
    from collections import defaultdict
    rng = np.random.default_rng(seed)

    if space_group is not None:
        sg   = gemmi.find_spacegroup_by_name(space_group)
        ops  = list(sg.operations())
        def _laue_key(h, k, l):
            candidates = set()
            for op in ops:
                hkl2 = tuple(op.apply_to_hkl([h, k, l]))
                candidates.add(hkl2)
                candidates.add((-hkl2[0], -hkl2[1], -hkl2[2]))  # Friedel mate
            return max(candidates)
    else:
        def _laue_key(h, k, l):  # type: ignore[misc]
            return max((h, k, l), (-h, -k, -l))

    groups: dict = defaultdict(list)
    for i in range(len(data)):
        key = _laue_key(int(data['h'][i]), int(data['k'][i]), int(data['l'][i]))
        groups[key].append(i)

    unique_keys = list(groups.keys())
    n_unique    = len(unique_keys)
    n_remove    = max(1, int(round(n_unique * fraction_remove)))
    chosen      = rng.choice(n_unique, size=n_remove, replace=False)
    remove_keys = {unique_keys[int(i)] for i in chosen}

    keep = np.ones(len(data), dtype=bool)
    for key in remove_keys:
        for idx in groups[key]:
            keep[idx] = False

    sg_note = f"space group {space_group}" if space_group else "Friedel-only grouping"
    return data[keep], (
        f"unique-hkl completeness reduction: removed {n_remove}/{n_unique} "
        f"unique reflections (~{fraction_remove*100:.0f}% target, {sg_note}); "
        f"{keep.sum()}/{len(data)} observations kept"
    )


def remove_cone(data, G, tilt_axis: np.ndarray | None = None,
                max_tilt_deg: float = 50.0):
    """Remove the missing cone of a 3D electron diffraction (3D-ED) tilt series.

    In a 3D-ED experiment the sample is tilted around a single axis over a
    limited angular range (typically ±40–70°).  Reflections whose reciprocal-
    space direction lies within (90° − max_tilt) of the tilt axis cannot be
    brought into diffraction condition and are absent from the dataset.

    Unlike remove_wedge (which removes a 2D azimuthal sector and is largely
    compensated by Laue-equivalent observations in other azimuths), this
    function removes a proper 3D cone.  For reflections close to the tilt axis
    ALL Laue equivalents are also in the cone, so there is nothing to compensate
    with — completeness genuinely drops, as it does in a real 3D-ED dataset.

    Angles are computed using the reciprocal metric tensor G so that the
    geometry is correct for non-orthogonal cells.

    tilt_axis: direction of the goniometer tilt axis in reciprocal fractional
        coordinates.  Default [0,1,0] (b* direction — natural choice for
        monoclinic structures where b is the unique axis).
    max_tilt_deg: maximum tilt angle in degrees (one-sided, symmetric ±).
        Typical 3D-ED values: 40–60°.  A smaller angle leaves a larger cone
        and lower completeness.
            max_tilt 60° → ~15% of data missing → completeness ~85%
            max_tilt 50° → ~23% of data missing → completeness ~75%
            max_tilt 45° → ~29% of data missing → completeness ~70%
        Exact completeness also depends on the space group symmetry and the
        orientation of the tilt axis relative to the crystal axes.

    Teaches: 3D-ED missing cone; the directional character of the data gap
    (different from random completeness loss); potential ADP distortion and
    residual density from the systematic direction-dependent data absence."""
    if tilt_axis is None:
        tilt_axis = np.array([0.0, 1.0, 0.0])
    tilt_axis = np.asarray(tilt_axis, dtype=float)
    tilt_axis = tilt_axis / np.linalg.norm(tilt_axis)

    hkl = np.stack([data["h"], data["k"], data["l"]], axis=1).astype(float)

    # Angle between each reflection and the tilt axis, using the proper
    # reciprocal metric so geometry is correct for non-orthogonal cells.
    # cos(θ) = (hkl · G · tilt_axis) / (|hkl|_G · |tilt_axis|_G)
    G_t    = G @ tilt_axis                                        # shape (3,)
    dot    = hkl @ G_t                                            # shape (n,)
    dstar2 = np.einsum("ij,jk,ik->i", hkl, G, hkl)
    dstar  = np.sqrt(np.maximum(dstar2, 1e-12))
    t_mag  = np.sqrt(float(tilt_axis @ G @ tilt_axis))

    cos_angle = np.abs(dot) / (dstar * t_mag + 1e-12)
    cos_angle = np.clip(cos_angle, 0.0, 1.0)

    # A reflection is MISSING when its direction is closer to the tilt axis
    # than (90° − max_tilt), i.e. |cos(angle with axis)| > sin(max_tilt).
    sin_max = np.sin(np.radians(max_tilt_deg))
    in_cone = cos_angle > sin_max
    keep    = ~in_cone

    n_removed = int(in_cone.sum())
    desc = (
        f"3D-ED missing cone: tilt_axis={tilt_axis.tolist()}, "
        f"max_tilt=±{max_tilt_deg}°, "
        f"{n_removed}/{len(data)} reflns removed ({n_removed/len(data)*100:.1f}%)"
    )
    return data[keep], desc


def remove_wedge(data, G, axis: str = "l",
                 frac_low: float = 0.0, frac_high: float = 1.0,
                 low_angle_bias: bool = False, d_bias: float | None = None):
    """Remove an angular WEDGE of reciprocal space to simulate inaccessible
    orientations (electron diffraction missing cone, high-pressure DAC shadowing,
    a crystal that could not be reoriented).

    Simplest, robust implementation: remove reflections whose direction falls in
    a band of azimuthal angle in a chosen reciprocal plane, OR (the pedagogically
    rich option) bias the removal toward LOW resolution so that completeness is
    worse at low angle than high -> produces the theta_full < theta_max signature
    (checkCIF: 'relatively more reflections missing at lower resolution').

    axis: which reciprocal axis is the wedge/rotation axis ('h','k','l').
    frac_low/frac_high: azimuthal band (fraction of 2*pi) to REMOVE.
    low_angle_bias: if True, additionally restrict removal to d > d_bias so the
                    missing wedge is concentrated at low angle.
    """
    hkl = np.stack([data["h"], data["k"], data["l"]], axis=1).astype(float)
    # azimuth in the plane perpendicular to the chosen axis
    idx = {"h": (1, 2), "k": (0, 2), "l": (0, 1)}[axis]
    az = np.arctan2(hkl[:, idx[1]], hkl[:, idx[0]])  # -pi..pi
    az = (az + 2 * np.pi) % (2 * np.pi)              # 0..2pi
    lo, hi = frac_low * 2 * np.pi, frac_high * 2 * np.pi
    in_wedge = (az >= lo) & (az < hi)
    if low_angle_bias:
        d = d_spacing(data, G)
        db = d_bias if d_bias is not None else np.median(d)
        in_wedge = in_wedge & (d > db)  # only remove low-angle part of the wedge
    keep = ~in_wedge
    desc = (f"wedge removed about {axis}*: azimuth [{frac_low:.2f},{frac_high:.2f}] "
            f"of 2pi, {(~keep).sum()}/{len(data)} reflns removed"
            + (f", low-angle biased (d>{(d_bias if d_bias else 'median'):})"
               if low_angle_bias else ""))
    return data[keep], desc


def simulate_weak_data(data, sigma_inflate: float = 1.0,
                       noise_frac: float = 0.0, seed: int = 0):
    """Simulate a weakly-diffracting crystal / short exposure: inflate sigmas
    and optionally add proportional noise to intensities. Pushes I/sigma down,
    effectively kills high-angle data, worsens R-factors.
    Teaches: the same end-effect as resolution loss but via data weakness;
    good contrast rung. sigma_inflate=2.0 doubles all sigmas."""
    rng = np.random.default_rng(seed)
    out = data.copy()
    out["sig"] = out["sig"] * sigma_inflate
    if noise_frac > 0:
        out["F2"] = out["F2"] + rng.normal(0.0, noise_frac * np.abs(out["F2"]))
    return out, f"weak-data sim: sigma x{sigma_inflate}, noise_frac={noise_frac}"


def inject_absorption_error(data, G, cell, mu_t: float = 1.0,
                            axis: np.ndarray | None = None):
    """HONEST absorption-error injection. REQUIRES unmerged data so that the
    per-observation direction is meaningful. Applies a smooth, direction-
    dependent transmission factor to F^2, simulating an UNCORRECTED absorption
    effect (as if the absorption correction were omitted/failed).

    Model: T(dir) = exp(-mu_t * (1 + cos^2 angle_to_axis)) ; F2 *= T, sig *= T.
    This is a teaching-grade approximation (not a real Gaussian/numerical
    absorption surface) but it is direction-dependent and systematic, which is
    the pedagogically important property: it cannot be seen in Mercury, only in
    residual density and data statistics.

    Teaches: spurious residual density (checkCIF PLAT097 family / Q-peaks),
    inflated/anisotropic ADPs, the 'invisible in the viewer' lesson.
    """
    hkl = np.stack([data["h"], data["k"], data["l"]], axis=1).astype(float)
    # crude direction proxy in reciprocal space
    v = hkl / (np.linalg.norm(hkl, axis=1, keepdims=True) + 1e-9)
    if axis is None:
        axis = np.array([1.0, 0.0, 0.0])
    axis = axis / np.linalg.norm(axis)
    cosang = v @ axis
    T = np.exp(-mu_t * (1.0 + cosang**2))
    out = data.copy()
    out["F2"] = out["F2"] * T
    out["sig"] = out["sig"] * T
    return out, f"absorption-error injected: mu_t={mu_t}, axis={axis.tolist()}"


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------

def ensure_list4(ins_text: str) -> str:
    """Make sure the .ins emits LIST 4 so checkCIF can do full FCF validation."""
    lines = ins_text.splitlines()
    has = any(ln.strip().upper().startswith("LIST 4") for ln in lines)
    if has:
        return ins_text
    out = []
    inserted = False
    for ln in lines:
        out.append(ln)
        if not inserted and ln.strip().upper().startswith("FVAR"):
            out.append("LIST 4")  # after FVAR is a safe spot
            inserted = True
    if not inserted:
        out.insert(0, "LIST 4")
    return "\n".join(out) + "\n"


def main():
    p = argparse.ArgumentParser(description="Generate a data-degradation ladder.")
    p.add_argument("name", help="basename of the source <name>.hkl / <name>.ins")
    p.add_argument("--cell", nargs=6, type=float, required=True,
                   metavar=("a", "b", "c", "alpha", "beta", "gamma"),
                   help="unit cell parameters (angstrom, degrees)")
    p.add_argument("--outdir", default="ladder", help="output directory root")
    args = p.parse_args()

    name = args.name
    hkl = read_hklf4(Path(f"{name}.hkl"))
    ins_text = ensure_list4(Path(f"{name}.ins").read_text())
    G = reciprocal_metric(tuple(args.cell))
    root = Path(args.outdir)

    d = d_spacing(hkl, G)
    print(f"Loaded {len(hkl)} reflections. d range "
          f"{d.min():.3f}-{d.max():.3f} A. Median d = {np.median(d):.3f} A.")
    print("Define your rungs below in the RUNGS list, then re-run.\n")

    # --- EDIT THIS: define your ladder here -------------------------------
    # Each rung: (tag, function-returning (data, desc))
    # The numbers below are STARTING POINTS for a high-res (<0.8 A) source;
    # see the companion .md for guidance on choosing them per structure.
    RUNGS = [
        ("00_reference",  lambda: (hkl, "untouched reference data (control)")),
        ("01_res_1p0",    lambda: truncate_resolution(hkl, G, d_min=1.0)),
        ("02_res_1p2",    lambda: truncate_resolution(hkl, G, d_min=1.2)),
        ("03_complete_88", lambda: reduce_completeness_random(hkl, 0.12, seed=1)),
        ("04_complete_80", lambda: reduce_completeness_random(hkl, 0.20, seed=1)),
        ("05_wedge",       lambda: remove_wedge(hkl, G, axis="l",
                                                frac_low=0.0, frac_high=0.20)),
        ("06_wedge_lowang", lambda: remove_wedge(hkl, G, axis="l",
                                                 frac_low=0.0, frac_high=0.30,
                                                 low_angle_bias=True)),
        ("07_weak",        lambda: simulate_weak_data(hkl, sigma_inflate=2.0)),
        ("08_absorption",  lambda: inject_absorption_error(hkl, G, args.cell,
                                                           mu_t=0.8)),
    ]
    # ----------------------------------------------------------------------

    for tag, fn in RUNGS:
        data, desc = fn()
        rd = root / f"rung_{tag}"
        write_hklf4(rd / f"{name}.hkl", data)
        (rd / f"{name}.ins").write_text(ins_text)
        # provenance stamp the instructor must keep
        (rd / "DEGRADATION.txt").write_text(
            f"TEACHING ARTEFACT — DELIBERATELY DEGRADED DATA\n"
            f"source: {name}\n"
            f"rung:   {tag}\n"
            f"op:     {desc}\n"
            f"NOTE: model atoms are unchanged from the correct structure.\n"
            f"This file is NOT the published structure and must never be\n"
            f"deposited or distributed as a real determination.\n"
        )
        print(f"[{tag:16s}] {desc}")

    print(f"\nWrote ladder to {root}/. Next: in each rung dir run `shelxl {name}`,\n"
          f"then build the CIF and FCF (see PROTOCOL in the .md).")


if __name__ == "__main__":
    main()
