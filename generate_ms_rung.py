#!/usr/bin/env python3
"""
generate_ms_rung.py — Missed-Symmetry (MS) rung generator.

INVERTED PRINCIPLE (read before using):
    The data-degradation pipeline never touches the model.  This module is the
    OPPOSITE: the .hkl reflection data is copied UNTOUCHED; only the model
    space group in .ins is downgraded to a subgroup by removing the inversion
    centre (the most common and pedagogically cleanest case).

    Lesson: a correct structure refined in the wrong (too-low) space group
    produces ADDSYM alerts (PLAT111/112/113) that PLATON's symmetry check fires
    specifically to catch this.  Mercury can hint at it geometrically, but only
    ADDSYM makes it unambiguous.

SUPPORTED OPERATION:
    Centrosymmetric → non-centrosymmetric subgroup by removing the automatic
    inversion centre (negating the LATT value).  The asymmetric unit doubles;
    inverted copies of all general-position atoms are generated automatically.

    More complex subgroup relationships (e.g. P212121 → P21212) are NOT
    supported by this script and must be constructed manually.

STABILITY WARNING (propagate into instructor notes):
    A centrosymmetric structure refined in a non-centrosymmetric subgroup
    typically yields a near-singular normal matrix.  SHELXL may produce
    meaningless ADPs or fail to converge.  Always inspect the .lst for
    NON-POSITIVE DEFINITE warnings and runaway R-factors.  The orchestrator
    (run_ladder.py) checks for these automatically and flags the rung if found.
"""
from __future__ import annotations
import shutil
from pathlib import Path

from generate_wa_rung import _join_continuations, _is_atom_line, _KEYWORDS


_SPECIAL_POSITION_THRESHOLD = 0.05  # fractional units; below = inversion centre


def _wrap(x: float) -> float:
    """Wrap fractional coordinate to [0, 1)."""
    return x % 1.0


def _frac_dist(a: float, b: float) -> float:
    """Minimum fractional distance along one axis (periodic)."""
    d = abs(a - b) % 1.0
    return min(d, 1.0 - d)


def generate_ms_rung(
    ins_path: Path,
    hkl_path: Path,
    output_dir: Path,
    name: str,
    drop_to_subgroup: str,
    shift_origin: list[float] | None,
    struct_id: str,
    note: str = '',
) -> str:
    """Generate a missed-symmetry rung directory.

    Removes the automatic inversion centre by negating the LATT value and
    doubles the asymmetric unit by adding inverted copies of all atoms that
    are NOT at (or very near) an inversion centre.

    drop_to_subgroup: human-readable name used only in the stamp and TITL
                      (e.g. 'P21', 'Cc', 'P1').  The actual symmetry change
                      is achieved mechanically by negating LATT.
    shift_origin:     optional [dx, dy, dz] fractional shift applied to all
                      coordinates BEFORE inversion (use if the subgroup needs
                      a non-standard origin).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    shift = list(shift_origin) if shift_origin else [0.0, 0.0, 0.0]

    raw     = ins_path.read_text().splitlines()
    logical = _join_continuations(raw)

    # ── First pass: collect SFAC, LATT, ZERR ─────────────────────────────────
    sfac_elements: list[str] = []
    orig_latt: int | None = None
    z_val: float = 0.0
    unit_counts: list[float] = []

    for line in logical:
        parts = line.split()
        if not parts:
            continue
        kw = parts[0].upper()
        if kw == 'SFAC':
            sfac_elements = [p.capitalize() for p in parts[1:]]
        elif kw == 'LATT' and len(parts) >= 2:
            orig_latt = int(parts[1])
        elif kw == 'ZERR' and len(parts) >= 2:
            try:
                z_val = float(parts[1])
            except ValueError:
                pass
        elif kw == 'UNIT' and len(parts) >= 2:
            try:
                unit_counts = [float(p) for p in parts[1:]]
            except ValueError:
                pass

    if orig_latt is None:
        raise ValueError(f"No LATT line found in {ins_path}")
    if orig_latt < 0:
        raise ValueError(
            f"LATT {orig_latt} is already non-centrosymmetric in {ins_path}.\n"
            f"MS rung (inversion removal) requires a centrosymmetric starting group.")

    new_latt = -orig_latt

    # ── Collect atom definitions ──────────────────────────────────────────────
    n_sfac = len(sfac_elements)
    orig_atoms: list[tuple[str, list[str]]] = []  # (label, parts)
    for line in logical:
        parts = line.split()
        if parts and _is_atom_line(parts, n_sfac):
            orig_atoms.append((parts[0], parts))

    existing_labels: set[str] = {label for label, _ in orig_atoms}

    def _unique_label(base: str) -> str:
        for suffix in ('p', 'A', 'B', 'C', 'D', 'E', 'F', 'G'):
            cand = (base[:3] + suffix) if len(base) >= 4 else (base + suffix)
            cand = cand[:4]  # SHELXL label max 4 chars
            if cand not in existing_labels:
                existing_labels.add(cand)
                return cand
        raise RuntimeError(f"Cannot generate unique label for '{base}'")

    # Build inverted atom lines
    inverted: list[str] = []
    skipped_special: list[str] = []

    for label, parts in orig_atoms:
        try:
            x = float(parts[2]) + shift[0]
            y = float(parts[3]) + shift[1]
            z = float(parts[4]) + shift[2]
        except (ValueError, IndexError):
            continue

        ix = _wrap(-x)
        iy = _wrap(-y)
        iz = _wrap(-z)

        # Skip if inverted position is within threshold of original (= special site)
        if (_frac_dist(ix, _wrap(x)) < _SPECIAL_POSITION_THRESHOLD and
                _frac_dist(iy, _wrap(y)) < _SPECIAL_POSITION_THRESHOLD and
                _frac_dist(iz, _wrap(z)) < _SPECIAL_POSITION_THRESHOLD):
            skipped_special.append(label)
            continue

        new_label = _unique_label(label)
        sfac_idx  = parts[1]
        sof       = parts[5] if len(parts) > 5 else '11.00000'
        u_params  = parts[6:] if len(parts) > 6 else ['0.05000']

        inv_line = (
            f"{new_label:<5s} {sfac_idx}"
            f"  {ix:10.6f}{iy:10.6f}{iz:10.6f}"
            f"  {sof}"
            + ('  ' + '  '.join(u_params) if u_params else '')
        )
        inverted.append(inv_line)

    # ── Second pass: rewrite .ins ─────────────────────────────────────────────
    out_lines: list[str] = []
    for line in logical:
        parts = line.split()
        if not parts:
            out_lines.append(line)
            continue
        kw = parts[0].upper()

        if kw == 'TITL':
            out_lines.append(
                f"TITL {name} in {drop_to_subgroup} "
                f"(TEACHING ARTEFACT — wrong space group from {struct_id})")
            continue

        if kw == 'LATT' and len(parts) >= 2:
            out_lines.append(f"LATT  {new_latt}")
            continue

        if kw == 'ZERR' and len(parts) >= 2:
            rest = '  '.join(parts[2:])
            try:
                z_new = float(parts[1]) * 2.0
                out_lines.append(f"ZERR  {z_new:.2f}  {rest}")
            except ValueError:
                out_lines.append(line)
            continue

        if kw == 'UNIT' and len(parts) >= 2:
            try:
                counts = [float(p) for p in parts[1:]]
                doubled = '  '.join(
                    str(int(c * 2)) if (c * 2) == int(c * 2)
                    else f"{c * 2:.4f}" for c in counts)
                out_lines.append(f"UNIT  {doubled}")
            except ValueError:
                out_lines.append(line)
            continue

        if kw == 'END':
            # Insert inverted atoms immediately before END
            for inv in inverted:
                out_lines.append(inv)
            out_lines.append(line)
            continue

        out_lines.append(line)

    # ── Write outputs ─────────────────────────────────────────────────────────
    (output_dir / f"{name}.ins").write_text('\n'.join(out_lines) + '\n')
    shutil.copy2(hkl_path, output_dir / f"{name}.hkl")

    desc = (
        f"missed symmetry: inversion removed (LATT {orig_latt} → {new_latt}), "
        f"subgroup {drop_to_subgroup}; "
        f"{len(inverted)} inverted atoms added to ASU"
        + (f"; {len(skipped_special)} near-special-position atoms not duplicated"
           if skipped_special else '')
        + (f"; {note}" if note else '')
    )

    stamp = (
        "TEACHING ARTEFACT — DELIBERATELY WRONG MODEL (MISSED SYMMETRY)\n"
        f"structure:       {struct_id}\n"
        f"original LATT:   {orig_latt}  (centrosymmetric — inversion included)\n"
        f"modified LATT:   {new_latt}  (non-centrosymmetric — inversion removed)\n"
        f"target subgroup: {drop_to_subgroup}\n"
        f"ASU expanded by: {len(inverted)} inverted atom copies\n"
    )
    if skipped_special:
        stamp += (f"near-inversion-centre atoms (NOT duplicated): "
                  f"{', '.join(skipped_special)}\n")
    if note:
        stamp += f"note: {note}\n"
    stamp += (
        "\n"
        "DATA:  the .hkl is the ORIGINAL, UNTOUCHED, correct reflection data.\n"
        "MODEL: the .ins uses a wrong (too low) space group.\n"
        "\n"
        "STABILITY WARNING:\n"
        "  Centrosymmetric structures in non-centrosymmetric subgroups often yield\n"
        "  near-singular normal matrices.  SHELXL may produce non-positive-definite\n"
        "  ADPs or fail to converge.  The orchestrator checks for these.\n"
        "  If the rung is flagged catastrophic, consider a different subgroup,\n"
        "  a different origin shift, or a different source structure.\n"
        "\n"
        "Expected diagnostics (local PLATON):\n"
        "  PLAT113 (Type_2) — 'ADDSYM Suggests Possible Pseudo/New Space-Group'\n"
        "  PLAT111 / PLAT112 — additional inversion / symmetry elements found\n"
        "  PLAT230 family   — degraded ADPs as a secondary consequence\n"
        "\n"
        "This file is NOT the published structure and must NEVER be deposited\n"
        "or distributed as a real determination.\n"
    )
    (output_dir / 'MODEL_MODIFICATION.txt').write_text(stamp)
    return desc
