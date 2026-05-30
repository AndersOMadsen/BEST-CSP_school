#!/usr/bin/env python3
"""
generate_ma_rung.py — Missing-Atoms (MA) rung generator.

INVERTED PRINCIPLE (read before using):
    The data-degradation pipeline never touches the model.  This module is the
    OPPOSITE: the .hkl reflection data is copied UNTOUCHED; only the model
    in .ins is modified by removing specified atoms (typically unmodelled
    solvent) from the atom list and adjusting the UNIT count.

    Lesson: a structure refined without accounting for all electron density
    produces characteristic PLATON alerts — residual density at the missing
    atom position, solvent-accessible voids, and CIF-consistency alerts from
    the formula/density mismatch.

FORMULA PRESERVATION:
    Unlike the WA rung (where SHELXL's recomputed formula is correct), for
    the MA rung the formula/density fields in the assembled CIF must carry
    the PUBLISHED values (which include the deleted atoms).  This mismatch
    is intentional: PLATON fires formula/density-consistency alerts because
    the declared formula includes atoms absent from the model.  These alerts
    are the diagnostic the student must learn to read.

    Formula preservation is the caller's responsibility: pass
        published_wins=('_chemical_formula', '_exptl_crystal_density_diffrn',
                        '_exptl_crystal_f_000', '_exptl_absorpt_coefficient_mu')
    to assemble_cif.merge_cif for this rung.

NOTE ON AFIX BLOCKS:
    This generator does NOT automatically remove AFIX instruction lines
    whose blocks become empty after deletion.  If deleted atoms are inside
    AFIX blocks, remove the AFIX instructions from the source .ins before
    running this generator (or do it manually after).  For jp2026 the water
    H atoms are free-standing (their AFIX was commented out in the .res),
    so this is not an issue for the intended use case.
"""
from __future__ import annotations
import shutil
from pathlib import Path

from generate_wa_rung import (
    _group_physical_lines, _is_atom_line,
    _general_multiplicity, _sof_fraction,
)

# SHELXL instruction keywords whose lines are dropped when they reference a
# deleted atom (exact base-label match after stripping _$N symmetry codes).
_ATOM_REF_KEYWORDS = {
    'HTAB', 'RTAB',
    'DFIX', 'DANG', 'SADI', 'SAME', 'RIGU', 'SIMU', 'DELU',
    'EADP', 'EXYZ', 'ISOR', 'FLAT', 'CHIV',
}


def _base_label(token: str) -> str:
    """Strip SHELXL symmetry code (e.g. _$2, _2) from an atom reference token."""
    return token.split('_')[0] if '_' in token else token


def _line_references_deleted(parts: list[str], delete_set: set[str]) -> bool:
    """Return True if any token in parts[1:] is (or refers to) a deleted atom."""
    return any(_base_label(t).upper() in delete_set for t in parts[1:])


def generate_ma_rung(
    ins_path: Path,
    hkl_path: Path,
    output_dir: Path,
    name: str,
    delete_atoms: list[str],
    struct_id: str,
) -> str:
    """Generate a missing-atoms rung directory.

    Removes delete_atoms from the .ins model and adjusts UNIT counts.
    The .hkl is copied untouched.

    Returns a one-line description for MODEL_MODIFICATION.txt.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    delete_set: set[str] = {a.upper() for a in delete_atoms}

    raw    = ins_path.read_text().splitlines()
    groups = _group_physical_lines(raw)

    # ── First pass: collect SFAC, UNIT, general multiplicity ─────────────────
    sfac_elements: list[str] = []
    unit_counts:   list[float] = []

    for logical, _ in groups:
        parts = logical.split()
        if not parts:
            continue
        kw = parts[0].upper()
        if kw == 'SFAC':
            sfac_elements = [p.capitalize() for p in parts[1:]]
        elif kw == 'UNIT' and len(parts) >= 2:
            try:
                unit_counts = [float(p) for p in parts[1:]]
            except ValueError:
                pass

    if not sfac_elements:
        raise ValueError(f"No SFAC line found in {ins_path}")

    n_sfac   = len(sfac_elements)
    gen_mult = _general_multiplicity(groups)

    # Pad unit_counts to n_sfac in case UNIT has fewer entries
    while len(unit_counts) < n_sfac:
        unit_counts.append(0.0)

    # Adjust UNIT for each deleted atom
    for logical, _ in groups:
        parts = logical.split()
        if not parts:
            continue
        if _is_atom_line(parts, n_sfac) and parts[0].upper() in delete_set:
            sfac_idx = int(parts[1])
            sof_frac = _sof_fraction(parts[5]) if len(parts) > 5 else 1.0
            delta    = gen_mult * sof_frac
            if sfac_idx - 1 < len(unit_counts):
                unit_counts[sfac_idx - 1] = max(0.0, unit_counts[sfac_idx - 1] - delta)

    # ── Second pass: rewrite .ins ─────────────────────────────────────────────
    out_parts:      list[str] = []
    unit_idx:       int | None = None
    removed_labels: list[str] = []

    for logical, phys in groups:
        parts = logical.split()
        if not parts:
            out_parts.append('\n'.join(phys))
            continue
        kw = parts[0].upper()

        if kw in ('L.S.', 'CGLS'):
            out_parts.append('L.S. 50')
            continue

        if kw == 'UNIT':
            unit_idx = len(out_parts)
            out_parts.append('')   # placeholder, filled after both passes
            continue

        # Remove atom lines for deleted atoms
        if _is_atom_line(parts, n_sfac) and parts[0].upper() in delete_set:
            removed_labels.append(parts[0])
            continue

        # Remove instruction lines that reference any deleted atom
        if kw in _ATOM_REF_KEYWORDS and _line_references_deleted(parts, delete_set):
            continue

        # Keep everything else verbatim (preserves original physical-line layout)
        out_parts.append('\n'.join(phys))

    # Fill UNIT placeholder
    if unit_idx is not None:
        out_parts[unit_idx] = (
            'UNIT  ' + '  '.join(
                str(int(c)) if c == int(c) else str(c)
                for c in unit_counts
            )
        )

    # ── Write outputs ─────────────────────────────────────────────────────────
    (output_dir / f"{name}.ins").write_text('\n'.join(out_parts) + '\n')
    shutil.copy2(hkl_path, output_dir / f"{name}.hkl")

    desc = (f"missing atoms: removed {', '.join(removed_labels or delete_atoms)} "
            f"from model; formula/density preserved from published CIF")

    stamp = (
        "TEACHING ARTEFACT — DELIBERATELY INCOMPLETE MODEL (MISSING ATOMS / UNMODELLED SOLVENT)\n"
        f"structure:     {struct_id}\n"
        f"modification:  {desc}\n"
        f"deleted atoms: {', '.join(removed_labels or delete_atoms)}\n"
        "\n"
        "DATA:  the .hkl is the ORIGINAL, UNTOUCHED, correct reflection data.\n"
        "MODEL: the .ins has solvent atoms removed from the atom list.\n"
        "       Surrounding atoms are free to relax toward the empty space\n"
        "       during refinement — this replicates what a refiner who missed\n"
        "       the solvent would actually see after completing their work.\n"
        "\n"
        "FORMULA NOTE:\n"
        "  The assembled CIF preserves the PUBLISHED formula and density\n"
        "  (which include the deleted atoms).  The mismatch between the\n"
        "  modelled atom list and the declared formula is INTENTIONAL:\n"
        "  PLATON fires formula/density-consistency alerts that are expected\n"
        "  diagnostics for this rung, not CIF-assembly errors.\n"
        "\n"
        "TEACHING FRAME:\n"
        "  This rung models 'what does unmodelled solvent look like in\n"
        "  checkCIF?'  The student's task is to read the void, residual-\n"
        "  density, and formula evidence and recognise that missing solvent\n"
        "  is present.  The deletion is the construction method; the lesson\n"
        "  is the diagnostic, not the deletion.\n"
        "\n"
        "Expected diagnostics (local PLATON):\n"
        "  PLAT097 family — largest residual density peak (water electrons\n"
        "                   pile up as a difference-density peak)\n"
        "  PLAT601 family — solvent-accessible void at the deleted position\n"
        "  PLAT041/043 family — formula / density mismatch (INTENDED)\n"
        "\n"
        "This file is NOT the published structure and must NEVER be deposited\n"
        "or distributed as a real determination.\n"
    )
    (output_dir / 'MODEL_MODIFICATION.txt').write_text(stamp)
    return desc
