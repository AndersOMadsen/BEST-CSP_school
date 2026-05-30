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


def _shelxl_wrap(logical: str, max_width: int = 76) -> str:
    """Re-wrap a logical SHELXL line into physical lines ≤ max_width chars.

    SHELXL requires continuation lines to start with a space character.
    Use this only for lines we generate ourselves; original lines should be
    written back verbatim via _group_physical_lines.
    """
    if len(logical) <= max_width:
        return logical
    tokens = logical.split()
    if not tokens:
        return logical
    physical: list[str] = []
    current = tokens[0]
    for token in tokens[1:]:
        if len(current) + 1 + len(token) <= max_width:
            current += ' ' + token
        else:
            physical.append(current + ' =')
            current = ' ' + token   # SHELXL: continuation lines must start with a space
    physical.append(current)
    return '\n'.join(physical)


def _group_physical_lines(raw_lines: list[str]) -> list[tuple[str, list[str]]]:
    """Group raw physical lines into (logical_content, physical_lines) pairs.

    Handles SHELXL '=' continuation.  The logical_content is the joined text
    (with the '=' stripped); physical_lines are the original source lines so
    that unmodified groups can be written back verbatim, preserving SHELXL's
    exact column layout and continuation style.
    """
    groups: list[tuple[str, list[str]]] = []
    buf_log = ''
    buf_phys: list[str] = []
    for line in raw_lines:
        stripped = line.rstrip('\n').rstrip()
        buf_phys.append(line.rstrip('\n'))
        if stripped.endswith('='):
            buf_log += stripped[:-1].rstrip() + ' '
        else:
            groups.append((buf_log + stripped, list(buf_phys)))
            buf_log = ''
            buf_phys = []
    if buf_phys:
        groups.append((buf_log, list(buf_phys)))
    return groups


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


# SHELXL LATT code → number of lattice points per unit cell (centering multiplicity)
# LATT 1=P, 2=I, 3=R(hex), 4=F, 5=A, 6=B, 7=C  (negative = non-centrosymmetric)
_LATT_CENTERING: dict[int, int] = {1: 1, 2: 2, 3: 3, 4: 4, 5: 2, 6: 2, 7: 2}


def _general_multiplicity(groups: list) -> int:
    """Return the general-position multiplicity from the LATT and SYMM cards.

    general_mult = centering_mult × (n_SYMM_cards + 1) × (2 if centrosymmetric else 1)

    This equals the number of symmetry-equivalent positions per unit cell for a
    general-position atom with SOF=1.0, which is exactly the per-cell contribution
    that one such ASU atom makes to the UNIT count.
    """
    latt: int | None = None
    n_symm: int = 0
    for logical, _ in groups:
        parts = logical.split()
        if not parts:
            continue
        kw = parts[0].upper()
        if kw == 'LATT' and len(parts) >= 2:
            try:
                latt = int(parts[1])
            except ValueError:
                pass
        elif kw == 'SYMM':
            n_symm += 1
    if latt is None:
        return 4  # safe fallback for P 21/n-like structures
    centering = _LATT_CENTERING.get(abs(latt), 1)
    centrosymmetric = latt > 0
    return centering * (n_symm + 1) * (2 if centrosymmetric else 1)


def _sof_fraction(sof_str: str) -> float:
    """Return the occupancy multiplier from a SHELXL SOF string.

    SHELXL encodes SOF as  (FVAR_index × 10) + occupancy_frac.
    E.g. '11.00000' → 1.0, '10.50000' → 0.5, '20.25000' → 0.25.
    Fixed SOFs (no FVAR linkage, e.g. '0.50000') also work.
    """
    try:
        val = abs(float(sof_str))
        fvar_code = int(val / 10)
        return val - fvar_code * 10
    except ValueError:
        return 1.0


def _relabel_for_element(old_label: str, from_elem: str, to_elem: str) -> str:
    """If the atom label starts with from_elem, replace that prefix with to_elem.

    E.g. C1 + C→N → N1,  Br1 + Br→Cl → Cl1.
    The SHELXL label maximum is 4 characters.
    """
    fe = from_elem.capitalize()
    te = to_elem.capitalize()
    if old_label.upper().startswith(fe.upper()):
        suffix = old_label[len(fe):]
        return (te + suffix)[:4]
    return old_label


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
    groups = _group_physical_lines(raw)

    # ── First pass: collect SFAC, ZERR, and all atom labels ──────────────────
    sfac_elements: list[str] = []
    z_val: float = 1.0
    existing_labels: set[str] = set()
    _n_sfac_tmp = 0
    for logical, _ in groups:
        parts = logical.split()
        if not parts:
            continue
        kw = parts[0].upper()
        if kw == 'SFAC':
            sfac_elements = [p.capitalize() for p in parts[1:]]
            _n_sfac_tmp = len(sfac_elements)
        elif kw == 'ZERR' and len(parts) >= 2:
            try:
                z_val = float(parts[1])
            except ValueError:
                pass
        elif _n_sfac_tmp and _is_atom_line(parts, _n_sfac_tmp):
            existing_labels.add(parts[0])

    if not sfac_elements:
        raise ValueError(f"No SFAC line found in {ins_path}")

    # Build element→SFAC-index map (1-based)
    elem_idx: dict[str, int] = {e.upper(): i + 1 for i, e in enumerate(sfac_elements)}

    # Count how many ASU atoms exist for each SFAC index.
    # Used to derive the per-cell contribution of one ASU atom:
    #   delta = UNIT[elem] / asu_count[elem]
    # e.g. 4 C atoms in ASU + UNIT[C]=16 → each C contributes 4 to the cell count.
    # This equals the site multiplicity for general-position atoms and is more
    # reliable than using Z from ZERR (which equals the formula multiplicity,
    # not the Wyckoff multiplicity of each atom).
    # General position multiplicity: per-cell contribution of one full-occupancy
    # general-position ASU atom.  Used to compute the correct UNIT delta.
    gen_mult = _general_multiplicity(groups)

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

    # ── Second pass: rewrite, preserving original physical lines where possible ─
    out_parts: list[str] = []
    applied_swaps: list[str] = []
    n_sfac = len(sfac_elements)
    unit_counts: list[float] | None = None
    unit_part_idx: int | None = None

    for logical, phys in groups:
        parts = logical.split()
        if not parts:
            out_parts.append('\n'.join(phys))
            continue
        kw = parts[0].upper()

        if kw in ('L.S.', 'CGLS'):
            out_parts.append('L.S. 50')
            continue

        if kw == 'SFAC':
            out_parts.append('SFAC  ' + '  '.join(sfac_elements))
            continue

        if kw == 'UNIT':
            try:
                unit_counts = [float(p) for p in parts[1:]]
                while len(unit_counts) < n_sfac:
                    unit_counts.append(0.0)
                unit_part_idx = len(out_parts)
                out_parts.append('')   # placeholder, filled after swap analysis
            except ValueError:
                out_parts.append('\n'.join(phys))
            continue

        if _is_atom_line(parts, n_sfac) and parts[0] in swap_map:
            label = parts[0]
            from_, to_ = swap_map[label]
            old_idx = elem_idx[from_]
            new_idx = elem_idx[to_]
            if unit_counts is not None:
                # Per-cell contribution = general_multiplicity × SOF_frac.
                # Works for any site symmetry: a special-position atom has a reduced
                # SOF (e.g. 0.5 on an inversion centre) that exactly compensates for
                # the lower site multiplicity, so gen_mult × SOF_frac is always correct.
                sof_frac_this = _sof_fraction(parts[5]) if len(parts) > 5 else 1.0
                delta = max(1, round(gen_mult * sof_frac_this))
                if old_idx - 1 < len(unit_counts):
                    unit_counts[old_idx - 1] = max(
                        0, unit_counts[old_idx - 1] - delta)
                while len(unit_counts) < new_idx:
                    unit_counts.append(0.0)
                unit_counts[new_idx - 1] += delta
            rest = parts[2:]   # x y z sof u_params…
            proposed = _relabel_for_element(label, from_, to_)
            # Avoid duplicate label: if proposed already exists, try To2, To3, …
            new_label = proposed
            if new_label in existing_labels and new_label != label:
                te = to_.capitalize()
                for n in range(1, 100):
                    candidate = (te + str(n))[:4]
                    if candidate not in existing_labels:
                        new_label = candidate
                        break
            existing_labels.discard(label)
            existing_labels.add(new_label)
            new_logical = f"{new_label:<5s} {new_idx}" + ''.join(f"  {p}" for p in rest)
            out_parts.append(_shelxl_wrap(new_logical))
            applied_swaps.append(
                f"  {label} → {new_label}: {from_} → {to_} (SFAC {old_idx} → {new_idx})")
            continue

        # Unmodified group — write original physical lines verbatim
        out_parts.append('\n'.join(phys))

    # Fill in UNIT placeholder
    if unit_part_idx is not None and unit_counts is not None:
        out_parts[unit_part_idx] = ('UNIT  ' +
            '  '.join(str(int(c)) if c == int(c) else str(c)
                      for c in unit_counts))

    # ── Write outputs ─────────────────────────────────────────────────────────
    (output_dir / f"{name}.ins").write_text('\n'.join(out_parts) + '\n')
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
