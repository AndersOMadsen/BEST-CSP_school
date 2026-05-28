#!/usr/bin/env python3
"""
generate_wa_rung.py — Wrong-Atom (WA) rung generator.

INVERTED PRINCIPLE (read before using):
    The data-degradation pipeline never touches the model.  This module is the
    OPPOSITE: the .hkl reflection data is copied UNTOUCHED; only the atomic
    model in .ins is changed by swapping the element type of one or more atoms.

    Lesson: the model itself can be wrong in ways that the data will not shout
    about.  PLATON catches this via the Hirshfeld rigid-bond test (PLAT230
    family) and, when the swap breaks pseudo-symmetry, via ADDSYM (PLAT113).

Callable as a library function from run_ladder.py.  Do NOT call degrade_data.py
from here; the HKL is pristine and must remain so.
"""
from __future__ import annotations
import shutil
from pathlib import Path


# ── SHELXL keyword set (to distinguish keywords from atom labels) ─────────────
_KEYWORDS = {
    'TITL', 'CELL', 'ZERR', 'LATT', 'SYMM', 'SFAC', 'UNIT', 'LAUE',
    'DISP', 'ACTA', 'LIST', 'BOND', 'CONF', 'WPDB', 'FMAP', 'GRID',
    'PLAN', 'MERG', 'SHEL', 'WGHT', 'FVAR', 'DEFS', 'SADI', 'DFIX',
    'DANG', 'CHIV', 'FLAT', 'DELU', 'SIMU', 'RIGU', 'ISOR', 'NCSY',
    'SUMP', 'L.S.', 'CGLS', 'BLOC', 'DAMP', 'STIR', 'PHAN', 'SPEC',
    'RESI', 'MOVE', 'ANIS', 'AFIX', 'HFIX', 'FRAG', 'FEND', 'EXYZ',
    'EADP', 'CONN', 'PART', 'BIND', 'FREE', 'REM', 'END', 'TWIN',
    'BASF', 'OMIT', 'SWAT', 'IREM', 'RTAB', 'MPLA', 'STOF', 'BUMP',
    'HTAB', 'SIZE', 'TEMP', 'SAME', 'TEXP', 'PRIG', 'MORE', 'MOLE',
}


def _join_continuations(raw_lines: list[str]) -> list[str]:
    """Join SHELXL continuation lines (trailing '=') into single logical lines."""
    joined: list[str] = []
    buf = ''
    for line in raw_lines:
        stripped = line.rstrip('\n').rstrip()
        if stripped.endswith('='):
            buf += stripped[:-1] + ' '
        else:
            joined.append(buf + stripped)
            buf = ''
    if buf:
        joined.append(buf)
    return joined


def _is_atom_line(parts: list[str], n_sfac: int) -> bool:
    """Return True if this logical line looks like a SHELXL atom definition."""
    if len(parts) < 6:
        return False
    label = parts[0]
    if not label[0].isalpha():
        return False
    if label.upper() in _KEYWORDS:
        return False
    try:
        t = int(parts[1])
    except ValueError:
        return False
    if not (1 <= t <= n_sfac):
        return False
    try:
        float(parts[2]); float(parts[3]); float(parts[4])
    except ValueError:
        return False
    return True


def generate_wa_rung(
    ins_path: Path,
    hkl_path: Path,
    output_dir: Path,
    name: str,
    swaps: list[dict],
    struct_id: str,
) -> str:
    """Generate a wrong-atom rung directory.

    swaps: list of {'atom': label, 'from_element': 'N', 'to_element': 'C'}

    Returns a one-line description for MODEL_MODIFICATION.txt.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    raw = ins_path.read_text().splitlines()
    logical = _join_continuations(raw)

    # ── First pass: collect SFAC and ZERR ─────────────────────────────────────
    sfac_elements: list[str] = []
    z_val: float = 1.0
    for line in logical:
        parts = line.split()
        if not parts:
            continue
        kw = parts[0].upper()
        if kw == 'SFAC':
            sfac_elements = [p.capitalize() for p in parts[1:]]
        elif kw == 'ZERR' and len(parts) >= 2:
            try:
                z_val = float(parts[1])
            except ValueError:
                pass

    if not sfac_elements:
        raise ValueError(f"No SFAC line found in {ins_path}")

    # Build element→SFAC-index map (1-based)
    elem_idx: dict[str, int] = {e.upper(): i + 1 for i, e in enumerate(sfac_elements)}

    # Validate swaps and collect any new elements needed
    swap_map: dict[str, tuple[str, str]] = {}
    new_elements: list[str] = []
    for s in swaps:
        atom  = s['atom']
        from_ = s['from_element'].upper()
        to_   = s['to_element'].upper()
        if from_ not in elem_idx:
            raise ValueError(
                f"WA rung: from_element '{from_}' not found in SFAC {sfac_elements}")
        if to_ not in elem_idx and to_.capitalize() not in [e.upper() for e in new_elements]:
            new_elements.append(to_.capitalize())
        swap_map[atom] = (from_, to_)

    # Add any new elements to SFAC
    for elem in new_elements:
        sfac_elements.append(elem)
        elem_idx[elem.upper()] = len(sfac_elements)

    # ── Second pass: rewrite lines ────────────────────────────────────────────
    out_lines: list[str] = []
    applied_swaps: list[str] = []
    n_sfac = len(sfac_elements)
    unit_counts: list[float] | None = None
    unit_line_pos: int | None = None

    for i, line in enumerate(logical):
        parts = line.split()
        if not parts:
            out_lines.append(line)
            continue
        kw = parts[0].upper()

        if kw == 'SFAC':
            out_lines.append('SFAC  ' + '  '.join(sfac_elements))
            continue

        if kw == 'UNIT':
            try:
                unit_counts = [float(p) for p in parts[1:]]
                while len(unit_counts) < n_sfac:
                    unit_counts.append(0.0)
                unit_line_pos = len(out_lines)
                out_lines.append('')  # placeholder, filled after swap analysis
            except ValueError:
                out_lines.append(line)
            continue

        if _is_atom_line(parts, n_sfac):
            label = parts[0]
            if label in swap_map:
                from_, to_ = swap_map[label]
                old_idx = elem_idx[from_]
                new_idx = elem_idx[to_]
                # Update UNIT counts: ±Z per swap (round Z to nearest int)
                if unit_counts is not None:
                    z_int = max(1, round(z_val))
                    if old_idx - 1 < len(unit_counts):
                        unit_counts[old_idx - 1] = max(
                            0, unit_counts[old_idx - 1] - z_int)
                    while len(unit_counts) < new_idx:
                        unit_counts.append(0.0)
                    unit_counts[new_idx - 1] += z_int
                # Replace the SFAC index in the line
                rest = parts[2:]   # x y z sof u_params...
                new_line = (f"{label:<5s} {new_idx}"
                            + ''.join(f"  {p}" for p in rest))
                out_lines.append(new_line)
                applied_swaps.append(
                    f"  {label}: {from_} → {to_} (SFAC {old_idx} → {new_idx})")
                continue

        out_lines.append(line)

    # Fill in UNIT placeholder
    if unit_line_pos is not None and unit_counts is not None:
        out_lines[unit_line_pos] = ('UNIT  ' +
            '  '.join(str(int(c)) if c == int(c) else str(c)
                      for c in unit_counts))

    # ── Write outputs ─────────────────────────────────────────────────────────
    (output_dir / f"{name}.ins").write_text('\n'.join(out_lines) + '\n')
    shutil.copy2(hkl_path, output_dir / f"{name}.hkl")

    swap_desc = '; '.join(
        f"{s['atom']} {s['from_element']}→{s['to_element']}" for s in swaps)
    desc = f"wrong-atom assignment: {swap_desc}"

    (output_dir / 'MODEL_MODIFICATION.txt').write_text(
        "TEACHING ARTEFACT — DELIBERATELY WRONG MODEL (WRONG ATOM ASSIGNMENT)\n"
        f"structure:     {struct_id}\n"
        f"modification:  {desc}\n"
        f"atom swaps:\n" + '\n'.join(applied_swaps) + "\n"
        "\n"
        "DATA:  the .hkl is the ORIGINAL, UNTOUCHED, correct reflection data.\n"
        "MODEL: the .ins carries wrong element assignments at the listed sites.\n"
        "\n"
        "Expected diagnostics (local PLATON):\n"
        "  PLAT230 family — Hirshfeld rigid-bond test flags non-physical ADP\n"
        "                   components when bond geometry is distorted by the swap\n"
        "  PLAT113/111    — ADDSYM may flag missed symmetry if the swap breaks\n"
        "                   pseudo-symmetry that the structure otherwise has\n"
        "  PLAT971/977    — residual density near the misassigned atom\n"
        "\n"
        "This file is NOT the published structure and must NEVER be deposited\n"
        "or distributed as a real determination.\n"
    )
    return desc
