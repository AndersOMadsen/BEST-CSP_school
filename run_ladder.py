#!/usr/bin/env python3
"""
run_ladder.py — Degradation → SHELXL → CIF assembly → PLATON → summary pipeline.

Usage:
    python run_ladder.py                         # all structures, all steps
    python run_ladder.py ej2019 wm5793          # specific structures only
    python run_ladder.py --steps generate        # only generate rung dirs
    python run_ladder.py --steps refine assemble validate summarize
    python run_ladder.py --dry-run               # print commands, do not execute
    python run_ladder.py ej2019 --steps summarize  # re-summarise after manual check

Steps (run in order):
    generate   — call degrade_data functions → write rung_*/  directories
    refine     — run shelxl <name> in each rung dir
    assemble   — merge published CIF header with SHELXL result (assemble_cif.py)
    validate   — run platon -u <name>.cif in each rung dir
    summarize  — parse .chk files → write ladder/summary.csv + summary.md

Prerequisites:
    pip install pyyaml gemmi numpy
    shelxl at /usr/local/bin/shelxl
    platon at /usr/local/bin/platon  (PLATON locates check.def automatically;
    if it cannot, set CHECKDEF=/path/to/check.def in the environment)
"""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

# ── locate modules relative to this script ────────────────────────────────────
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

try:
    import yaml
except ImportError:
    sys.exit("ERROR: PyYAML not found.  Run: pip install pyyaml")

import degrade_data as dd
from assemble_cif import merge_cif
from parse_platon import parse_chk, parse_ckf
from generate_ms_rung import generate_ms_rung
from generate_wa_rung import generate_wa_rung

# ── tool paths ────────────────────────────────────────────────────────────────
SHELXL = '/usr/local/bin/shelxl'
PLATON = '/usr/local/bin/platon'

ALL_STEPS = ('generate', 'refine', 'assemble', 'validate', 'summarize')


# ── rung dispatch ─────────────────────────────────────────────────────────────

def apply_rung_op(cfg: dict, hkl: np.ndarray,
                  G: np.ndarray,
                  space_group: str | None = None) -> tuple[np.ndarray, str]:
    """Apply one rung's degradation operation.  Returns (data, description)."""
    op = cfg['op']
    if op == 'reference':
        return hkl.copy(), "untouched reference data (control)"
    if op == 'truncate_resolution':
        return dd.truncate_resolution(hkl, G, cfg['d_min'])
    if op == 'reduce_completeness_random':
        return dd.reduce_completeness_random(
            hkl, cfg['fraction_remove'], cfg.get('seed', 0))
    if op == 'reduce_completeness_unique':
        return dd.reduce_completeness_unique(
            hkl, cfg['fraction_remove'], cfg.get('seed', 0),
            space_group=space_group)
    if op == 'remove_cone':
        tilt_cfg = cfg.get('tilt_axis')
        tilt_axis = np.array(tilt_cfg, dtype=float) if tilt_cfg is not None else None
        return dd.remove_cone(
            hkl, G,
            tilt_axis=tilt_axis,
            max_tilt_deg=cfg.get('max_tilt_deg', 50.0),
        )
    if op == 'remove_wedge':
        return dd.remove_wedge(
            hkl, G,
            axis=cfg.get('axis', 'l'),
            frac_low=cfg.get('frac_low', 0.0),
            frac_high=cfg.get('frac_high', 0.25),
            low_angle_bias=cfg.get('low_angle_bias', False),
            d_bias=cfg.get('d_bias', None),
        )
    if op == 'simulate_weak_data':
        return dd.simulate_weak_data(
            hkl,
            sigma_inflate=cfg.get('sigma_inflate', 2.0),
            noise_frac=cfg.get('noise_frac', 0.0),
            seed=cfg.get('seed', 0),
        )
    if op == 'inject_absorption_error':
        axis_cfg = cfg.get('axis')
        axis = np.array(axis_cfg, dtype=float) if axis_cfg is not None else None
        return dd.inject_absorption_error(
            hkl, G, None,  # 'cell' param exists in signature but is unused
            mu_t=cfg.get('mu_t', 0.8),
            axis=axis,
        )
    raise ValueError(f"Unknown rung op: {cfg['op']!r}")


# ── Step 1: generate rung directories ────────────────────────────────────────

def step_generate(struct: dict, struct_dir: Path,
                  dry_run: bool = False) -> list[Path]:
    """Write rung_*/ directories with degraded HKL + copied INS + stamp."""
    name = struct['shelx_name']
    hkl_path = struct_dir / f"{name}.hkl"
    ins_path  = struct_dir / f"{name}.ins"

    for p in (hkl_path, ins_path):
        if not p.exists():
            sys.exit(f"ERROR: required file not found: {p}")

    hkl = dd.read_hklf4(hkl_path)
    ins_text = dd.ensure_list4(ins_path.read_text())
    G = dd.reciprocal_metric(tuple(struct['cell']))

    d = dd.d_spacing(hkl, G)
    s_max = 1.0 / (2.0 * d.min())
    print(f"    {len(hkl)} reflns,  d = {d.min():.3f}–{d.max():.3f} Å"
          f"  (sinθ/λ max = {s_max:.3f} Å⁻¹)")

    ladder_root = struct_dir / 'ladder'
    rung_dirs: list[Path] = []

    for rung_cfg in struct['rungs']:
        tag      = rung_cfg['tag']
        rung_dir = ladder_root / f"rung_{tag}"

        data, desc = apply_rung_op(rung_cfg, hkl, G,
                                   space_group=struct.get('space_group'))
        print(f"    [{tag}]  {len(data)} reflns  — {desc}")

        if dry_run:
            rung_dirs.append(rung_dir)
            continue

        rung_dir.mkdir(parents=True, exist_ok=True)
        dd.write_hklf4(rung_dir / f"{name}.hkl", data)
        (rung_dir / f"{name}.ins").write_text(ins_text)
        (rung_dir / 'DEGRADATION.txt').write_text(
            "TEACHING ARTEFACT — DELIBERATELY DEGRADED DATA\n"
            f"source:    {name}   (structure id: {struct['id']})\n"
            f"rung:      {tag}\n"
            f"op:        {desc}\n"
            "NOTE:      model atoms are unchanged from the correct published structure.\n"
            "IMPORTANT: this file must NEVER be deposited or distributed as a\n"
            "           real crystal structure determination.\n"
        )
        rung_dirs.append(rung_dir)

    # ── Model-error rungs (MS and WA) — generated after data rungs ───────────
    ins_path = struct_dir / f"{name}.ins"
    hkl_path = struct_dir / f"{name}.hkl"
    pub_cif  = struct_dir / struct.get('published_cif', '')

    ms_cfg = struct.get('ms_rung', {})
    if ms_cfg.get('enabled'):
        tag      = 'ms'
        rung_dir = ladder_root / f"rung_{tag}"
        subgroup = ms_cfg.get('drop_to_subgroup', '?')
        shift    = ms_cfg.get('shift_to_origin')
        note     = ms_cfg.get('note', '')
        print(f"    [ms]  missed-symmetry rung → {subgroup}")
        if not dry_run:
            desc = generate_ms_rung(ins_path, hkl_path, rung_dir,
                                    name, subgroup, shift, struct['id'], note)
            print(f"          {desc}")
        rung_dirs.append(rung_dir)

    wa_cfg = struct.get('wa_rung', {})
    if wa_cfg.get('enabled'):
        tag      = 'wa'
        rung_dir = ladder_root / f"rung_{tag}"
        sw       = wa_cfg.get('swaps', [])
        print(f"    [wa]  wrong-atom rung — "
              + ', '.join(f"{s['atom']} {s['from_element']}→{s['to_element']}"
                          for s in sw))
        if not dry_run:
            desc = generate_wa_rung(ins_path, hkl_path, rung_dir,
                                    name, sw, struct['id'])
            print(f"          {desc}")
        rung_dirs.append(rung_dir)

    return rung_dirs


# ── Step 2: SHELXL refinement + sanity gate ───────────────────────────────────

def _check_shelxl_sanity(lst_path: Path, name: str) -> tuple[bool, str]:
    """Parse SHELXL .lst; return (is_ok, warning_message_or_empty)."""
    if not lst_path.exists():
        return True, ''
    text = lst_path.read_text(errors='replace').upper()
    # Non-positive-definite ADPs
    if 'NON-POSITIVE DEFINITE' in text or 'NPD' in text:
        return False, "non-positive-definite ADPs detected in .lst"
    # Diverged R-factor
    import re as _re
    m = _re.search(r'R1\s*=\s*([\d.]+)\s+FOR', text)
    if m and float(m.group(1)) > 0.50:
        return False, f"R1 = {float(m.group(1)):.3f} — refinement diverged (> 0.50)"
    # SHELXL explicitly says not converged
    if '** NOT CONVERGED **' in text or 'NOT CONVERGE' in text:
        return False, "SHELXL reports refinement did not converge"
    return True, ''


def step_refine(struct: dict, rung_dir: Path, dry_run: bool = False,
                is_model_rung: bool = False) -> bool:
    """Run shelxl <name> in rung_dir.  Returns True on success.

    For model-error rungs (is_model_rung=True) the sanity gate is applied
    and a CATASTROPHIC.txt stamp is written if the refinement is broken.
    """
    name = struct['shelx_name']
    cmd  = [SHELXL, name]
    if dry_run:
        print(f"    DRY-RUN: (cd {rung_dir.name} && {' '.join(cmd)})")
        return True

    result = subprocess.run(cmd, cwd=rung_dir,
                            capture_output=True, text=True, timeout=600)
    res_path = rung_dir / f"{name}.res"
    if not res_path.exists():
        print(f"    ERROR: SHELXL produced no .res for {rung_dir.name}")
        if result.stdout:
            print(result.stdout[-2000:])
        return False

    # Sanity gate for model-error rungs (and optionally for all)
    lst_path = rung_dir / f"{name}.lst"
    ok, warning = _check_shelxl_sanity(lst_path, name)
    if not ok:
        msg = (
            f"    WARNING: SHELXL sanity check FAILED for {rung_dir.name}\n"
            f"    → {warning}\n"
            f"    This rung is CATASTROPHIC — do not use its results for teaching.\n"
            f"    Instructor action: choose a different subgroup/swap or source structure."
        )
        print(msg)
        (rung_dir / 'CATASTROPHIC.txt').write_text(
            "RUNG FLAGGED AS CATASTROPHIC BY SANITY GATE\n"
            f"reason: {warning}\n"
            "The refinement did not converge to a meaningful result.\n"
            "Do NOT use this rung for teaching until the issue is resolved.\n"
            "Suggested actions:\n"
            "  MS rung: try a different origin shift, or a different structure.\n"
            "  WA rung: try a more conservative element swap (e.g. C↔N not O↔F).\n"
        )
        if is_model_rung:
            return False  # block further pipeline steps for model-error rungs

    return True


# ── Step 3: assemble merged CIF ──────────────────────────────────────────────

def step_assemble(struct: dict, rung_dir: Path,
                  struct_dir: Path, dry_run: bool = False) -> bool:
    """Merge published CIF header into SHELXL CIF for this rung."""
    name       = struct['shelx_name']
    shelxl_cif = rung_dir / f"{name}.cif"
    pub_cif    = struct_dir / struct['published_cif']

    if not shelxl_cif.exists():
        print(f"    SKIP assemble: {shelxl_cif.name} not found "
              f"(does I.ins contain ACTA?)")
        return False
    if not pub_cif.exists():
        print(f"    SKIP assemble: published CIF not found: {pub_cif}")
        return False
    if dry_run:
        print(f"    DRY-RUN: merge_cif({pub_cif.name}, {shelxl_cif.name})")
        return True

    merge_cif(pub_cif, shelxl_cif, shelxl_cif)
    return True


# ── Step 4: PLATON validation ─────────────────────────────────────────────────

def step_validate(struct: dict, rung_dir: Path, dry_run: bool = False) -> bool:
    """Run platon -u <name>.cif; keep .chk and .ckf."""
    name     = struct['shelx_name']
    cif_path = rung_dir / f"{name}.cif"

    if not cif_path.exists():
        print(f"    SKIP validate: {cif_path.name} not found")
        return False

    env = os.environ.copy()
    env['DISPLAY'] = ''   # run headless (no X11 needed for -u mode)
    cmd = [PLATON, '-u', f"{name}.cif"]

    if dry_run:
        print(f"    DRY-RUN: (cd {rung_dir.name} && DISPLAY= {' '.join(cmd)})")
        return True

    try:
        subprocess.run(cmd, cwd=rung_dir, env=env,
                       capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        print(f"    WARNING: PLATON timed out for {rung_dir.name}")
        return False

    chk_path = rung_dir / f"{name}.chk"
    if not chk_path.exists():
        print(f"    ERROR: PLATON produced no .chk for {rung_dir.name}\n"
              f"    If check.def cannot be located, set:  "
              f"export CHECKDEF=/path/to/check.def")
        return False

    ckf_path = rung_dir / f"{name}.ckf"
    if not ckf_path.exists():
        print(f"    NOTE: no .ckf produced (FCF may be missing or "
              f"PLATON could not pair it with the CIF)")

    return True


# ── Step 5: summarize ─────────────────────────────────────────────────────────

def _read_op_desc(rung_dir: Path) -> str:
    """Read the operation description from a rung's stamp file."""
    # Data-degradation rungs use DEGRADATION.txt (op: line)
    deg = rung_dir / 'DEGRADATION.txt'
    if deg.exists():
        for line in deg.read_text().splitlines():
            if line.startswith('op:'):
                return line[3:].strip()
    # Model-error rungs use MODEL_MODIFICATION.txt (modification: line)
    mod = rung_dir / 'MODEL_MODIFICATION.txt'
    if mod.exists():
        for line in mod.read_text().splitlines():
            if line.startswith('modification:'):
                return line[13:].strip()
    return ''


def _rung_is_catastrophic(rung_dir: Path) -> bool:
    return (rung_dir / 'CATASTROPHIC.txt').exists()


def step_summarize(struct: dict, struct_dir: Path) -> None:
    """Parse .chk and .ckf files → ladder/summary.csv and ladder/summary.md.

    Processes ALL rung_*/ directories (data-degradation AND model-error rungs).
    """
    name        = struct['shelx_name']
    ladder_root = struct_dir / 'ladder'

    # Build ordered list of (tag, rung_dir) from all rung_*/ directories,
    # then overlay with YAML rung ordering for data-degradation rungs.
    yaml_tags = [rc['tag'] for rc in struct.get('rungs', [])]
    all_rung_dirs = sorted(ladder_root.glob('rung_*/'))

    # Ordered: yaml rungs first (in YAML order), then any extra dirs (ms, wa)
    ordered_tags: list[str] = list(yaml_tags)
    for rd in all_rung_dirs:
        tag = rd.name.removeprefix('rung_')
        if tag not in ordered_tags:
            ordered_tags.append(tag)

    rows: list[dict] = []
    ref_alert_codes: set[str] = set()

    for tag in ordered_tags:
        rung_dir = ladder_root / f"rung_{tag}"
        if not rung_dir.is_dir():
            continue
        chk_path = rung_dir / f"{name}.chk"
        ckf_path = rung_dir / f"{name}.ckf"

        op_desc = _read_op_desc(rung_dir)
        # Fallback: use op from YAML config if stamp not yet written
        if not op_desc:
            for rc in struct.get('rungs', []):
                if rc.get('tag') == tag:
                    op_desc = rc.get('op', tag)
                    break

        row: dict = {
            # ── Identity ──────────────────────────────────────────────────────
            'rung':                  tag,
            'op':                    op_desc,
            'catastrophic':          'YES' if _rung_is_catastrophic(rung_dir) else '',
            # ── Refinement quality (.chk) ─────────────────────────────────────
            'R1':                    '',
            'wR2':                   '',
            'GooF':                  '',
            'rint':                  '',   # internal R between equiv. observations
            'data_param_ratio':      '',
            'rho_max':               '',
            'resolution_A':          '',
            # ── Completeness (.chk + .ckf) ────────────────────────────────────
            'completeness':          '',   # overall (from .chk Expected Ratio)
            'completeness_acta':     '',   # at sin(th)/lam = 0.600 (.ckf Sec 4)
            'n_missing_below_acta':  '',   # missing in Acta band (.ckf Sec 6)
            # ── Data quality — structure-factor report (.ckf) ─────────────────
            'obs_fraction':          '',   # fraction of unique with I > 2σ
            'isig_last_shell':       '',   # I/σ in outermost shell (weak-data key)
            'pct_obs_last_shell':    '',   # % I > 2σ in outermost shell
            # ── Alerts (.chk) ─────────────────────────────────────────────────
            'alerts_A':              0,
            'alerts_B':              0,
            'alerts_C':              0,
            'alerts_G':              0,
            'new_alert_codes':       '',
            'unexpected_type1':      '',
        }

        if not chk_path.exists():
            row['op'] = op_desc + '  [NO .chk — PLATON not yet run]'
        else:
            # ── Parse .chk ────────────────────────────────────────────────────
            s = parse_chk(chk_path)
            row.update({
                'R1':               f"{s.r1:.4f}"           if s.r1  is not None else '',
                'wR2':              f"{s.wr2:.4f}"          if s.wr2 is not None else '',
                'GooF':             f"{s.goof:.3f}"         if s.goof is not None else '',
                'rint':             f"{s.rint:.3f}"         if s.rint is not None else '',
                'data_param_ratio': f"{s.data_param_ratio}" if s.data_param_ratio else '',
                'rho_max':          f"{s.rho_max:.2f}"      if s.rho_max is not None else '',
                'resolution_A':     f"{s.resolution:.3f}"   if s.resolution else '',
                'completeness':     f"{s.completeness*100:.1f}%" if s.completeness else '',
                'alerts_A':         s.alert_counts.get('A', 0),
                'alerts_B':         s.alert_counts.get('B', 0),
                'alerts_C':         s.alert_counts.get('C', 0),
                'alerts_G':         s.alert_counts.get('G', 0),
            })

            this_codes = {a.code for a in s.alerts}
            if tag.startswith('00_'):
                ref_alert_codes = this_codes
            else:
                new_codes = this_codes - ref_alert_codes
                row['new_alert_codes'] = ' '.join(sorted(new_codes))
                # G-level Type_1 alerts are geometry comparisons (calc vs rep)
                # that fire whenever the model changes — not assembly errors.
                unexpected = [
                    a for a in s.alerts
                    if a.code not in ref_alert_codes
                    and a.is_type1()
                    and a.level in ('A', 'B', 'C')
                ]
                if unexpected:
                    row['unexpected_type1'] = '; '.join(
                        f"{a.code}_{a.level} {a.text[:60]}" for a in unexpected
                    )

            # ── Parse .ckf (structure-factor report) ──────────────────────────
            if ckf_path.exists():
                k = parse_ckf(ckf_path)
                row.update({
                    'completeness_acta':    (f"{k.completeness_acta*100:.1f}%"
                                             if k.completeness_acta is not None else ''),
                    'n_missing_below_acta': (str(k.n_missing_below_acta)
                                             if k.n_missing_below_acta is not None else ''),
                    'obs_fraction':         (f"{k.obs_fraction*100:.1f}%"
                                             if k.obs_fraction is not None else ''),
                    'isig_last_shell':      (f"{k.isig_last_shell:.2f}"
                                             if k.isig_last_shell is not None else ''),
                    'pct_obs_last_shell':   (f"{k.pct_obs_last_shell:.1f}%"
                                             if k.pct_obs_last_shell is not None else ''),
                })

        rows.append(row)

    if not rows:
        print(f"    No rungs found in {ladder_root}")
        return

    # ── CSV ───────────────────────────────────────────────────────────────────
    csv_path = ladder_root / 'summary.csv'
    fieldnames = list(rows[0].keys())
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"    CSV  → {csv_path.relative_to(_HERE)}")

    # ── Markdown — split into two tables for readability ──────────────────────
    md_path = ladder_root / 'summary.md'
    with open(md_path, 'w') as f:
        f.write(f"# PLATON/FCF Degradation Ladder — {struct['id']}\n\n")
        f.write(f"Radiation: **{struct['radiation']} Kα** "
                f"(λ = {struct['wavelength']} Å) · "
                f"Space group: {struct.get('space_group', '?')} · "
                f"Cell: {struct['cell']}\n\n")
        f.write(
            "> **`new_alert_codes`** = PLATON alert codes new in this rung "
            "(absent in rung_00_reference).  \n"
            "> **`unexpected_type1`** = Type-1 (CIF construction) alerts that "
            "are new; if non-empty, check the CIF assembly step.  \n"
            "> **`isig_last_shell`** / **`pct_obs_last_shell`** = I/σ and "
            "fraction observed in the outermost resolution shell "
            "— the primary diagnostic for weak data (GooF < 1 = sigmas "
            "over-estimated).\n\n"
        )

        # Table 1: refinement + completeness + alerts
        cols1 = [
            'rung', 'catastrophic', 'R1', 'wR2', 'GooF', 'rint',
            'data_param_ratio', 'completeness', 'completeness_acta',
            'rho_max', 'resolution_A',
            'alerts_A', 'alerts_B', 'alerts_C', 'new_alert_codes',
        ]
        f.write("## Refinement & alert summary\n\n")
        f.write('| ' + ' | '.join(cols1) + ' |\n')
        f.write('| ' + ' | '.join(':---' for _ in cols1) + ' |\n')
        for row in rows:
            f.write('| ' + ' | '.join(str(row.get(c, '')) for c in cols1) + ' |\n')

        # Table 2: structure-factor report (the student-facing data quality view)
        cols2 = [
            'rung', 'obs_fraction', 'isig_last_shell', 'pct_obs_last_shell',
            'n_missing_below_acta', 'unexpected_type1',
        ]
        f.write("\n## Structure-factor report (data quality)\n\n")
        f.write(
            "| rung | obs_fraction | isig_last_shell | pct_obs_last_shell"
            " | n_missing_below_acta | unexpected_type1 |\n"
        )
        f.write('| ' + ' | '.join(':---' for _ in cols2) + ' |\n')
        for row in rows:
            f.write('| ' + ' | '.join(str(row.get(c, '')) for c in cols2) + ' |\n')

        f.write(
            "\n*`obs_fraction` = unique reflections with I > 2σ / total unique. "
            "`isig_last_shell` and `pct_obs_last_shell` are from the outermost "
            "resolution shell — both drop sharply for weak data while completeness "
            "stays at 100%.*\n"
        )

    print(f"    MD   → {md_path.relative_to(_HERE)}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Crystallographic degradation ladder pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('structures', nargs='*',
                    help="Structure IDs to process (default: all in structures.yaml)")
    ap.add_argument('--config', default=str(_HERE / 'structures.yaml'),
                    help="Path to structures.yaml")
    ap.add_argument('--steps', nargs='+', choices=ALL_STEPS, default=list(ALL_STEPS),
                    metavar='STEP',
                    help=f"Steps to run (default: all).  Choices: {', '.join(ALL_STEPS)}")
    ap.add_argument('--dry-run', action='store_true',
                    help="Print what would run; do not execute SHELXL or PLATON")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        sys.exit(f"ERROR: config not found: {cfg_path}")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    base_dir = cfg_path.parent.resolve()
    structs  = cfg['structures']

    if args.structures:
        structs = [s for s in structs if s['id'] in args.structures]
        if not structs:
            sys.exit(f"ERROR: no structures matching {args.structures!r} "
                     f"in {cfg_path.name}")

    steps = set(args.steps)

    for struct in structs:
        sid = struct['id']
        print(f"\n{'='*64}")
        print(f"  {sid}  ({struct['radiation']} Kα,  λ = {struct['wavelength']} Å)")
        print(f"{'='*64}")

        struct_dir = base_dir / struct['path']
        if not struct_dir.is_dir():
            print(f"  ERROR: structure directory not found: {struct_dir}")
            continue

        # Collect rung directories for steps that don't regenerate them
        if 'generate' in steps:
            print("  [generate]")
            rung_dirs = step_generate(struct, struct_dir, dry_run=args.dry_run)
        else:
            rung_dirs = sorted((struct_dir / 'ladder').glob('rung_*/'))
            if not rung_dirs:
                print("  No rung_*/ directories found — run with --steps generate first")
                continue

        for rung_dir in rung_dirs:
            tag            = rung_dir.name.removeprefix('rung_')
            is_model_rung  = tag in ('ms', 'wa')
            print(f"\n  Rung: {tag}"
                  + ("  [MODEL-ERROR RUNG]" if is_model_rung else ""))

            if 'refine' in steps:
                ok = step_refine(struct, rung_dir, dry_run=args.dry_run,
                                 is_model_rung=is_model_rung)
                if not ok:
                    print(f"  Skipping assemble/validate for {tag} (shelxl failed)")
                    continue

            if 'assemble' in steps:
                step_assemble(struct, rung_dir, struct_dir, dry_run=args.dry_run)

            if 'validate' in steps:
                step_validate(struct, rung_dir, dry_run=args.dry_run)

        if 'summarize' in steps and not args.dry_run:
            print(f"\n  [summarize]")
            step_summarize(struct, struct_dir)

    print(f"\n{'='*64}")
    print("Done.")


if __name__ == '__main__':
    main()
