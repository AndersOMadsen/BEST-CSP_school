#!/usr/bin/env python3
"""parse_platon.py — Parse PLATON .chk and .ckf output for the degradation pipeline."""
from __future__ import annotations
import math
import re
from dataclasses import dataclass, field
from pathlib import Path


# ── .chk types ────────────────────────────────────────────────────────────────

@dataclass
class Alert:
    code: str
    alert_type: str   # '1'–'4': CIF-construction / crystallographic / chemical / cosmetic
    level: str        # 'A', 'B', 'C', or 'G'
    text: str

    def is_type1(self) -> bool:
        """Type 1 = CIF construction / syntax / metadata alert."""
        return self.alert_type == '1'


@dataclass
class PlatonStats:
    """Data extracted from a PLATON .chk file."""
    rint: float | None = None            # internal R-factor between equiv. observations
    r1: float | None = None
    wr2: float | None = None
    goof: float | None = None
    nref_obs: int | None = None          # reflections in wR2 set
    npar: int | None = None
    data_param_ratio: float | None = None
    completeness: float | None = None    # fraction 0–1 (from Expected Ratio)
    rho_min: float | None = None
    rho_max: float | None = None
    resolution: float | None = None      # d_min in Å from theta_max + wavelength
    alerts: list[Alert] = field(default_factory=list)
    alert_counts: dict[str, int] = field(
        default_factory=lambda: {'A': 0, 'B': 0, 'C': 0, 'G': 0})


def parse_chk(chk_path: Path) -> PlatonStats:
    """Parse a PLATON .chk file; return populated PlatonStats."""
    text = chk_path.read_text(errors='replace')
    stats = PlatonStats()

    # ── Alerts ────────────────────────────────────────────────────────────────
    # Format: "183_ALERT_1_A Missing _cell_measurement_reflns_used Value ..."
    for m in re.finditer(r'^(\d+)_ALERT_(\d+)_([ABCG])\s+(.*)', text, re.MULTILINE):
        a = Alert(
            code=m.group(1),
            alert_type=m.group(2),
            level=m.group(3),
            text=m.group(4).strip(),
        )
        stats.alerts.append(a)
        stats.alert_counts[a.level] = stats.alert_counts.get(a.level, 0) + 1

    # ── R(int) ────────────────────────────────────────────────────────────────
    # "# X-ray MoKa   R(int) = 0.080,  wR2/R(int) =  1.9,  Nref/Npar = 10.4"
    m = re.search(r'R\(int\)\s*=\s*([\d.]+)', text)
    if m:
        stats.rint = float(m.group(1))

    # ── R-factors (from the CIF+FCF data line in the header) ─────────────────
    # "# R= 0.0247(  8033), wR2= 0.0645(  8581), S = 1.035     (From CIF+FCF data -IAM)"
    r_pat = re.compile(
        r'#\s+R=\s*([\d.]+)\(\s*\d+\),\s*wR2=\s*([\d.]+)\(\s*(\d+)\),'
        r'\s*S\s*=\s*([\d.]+).*?From CIF\+FCF',
        re.DOTALL,
    )
    m = r_pat.search(text)
    if m:
        stats.r1       = float(m.group(1))
        stats.wr2      = float(m.group(2))
        stats.nref_obs = int(m.group(3))
        stats.goof     = float(m.group(4))

    # Npar from "... S = 1.035, Npar=  140, Flack ..." (the third R= line).
    # Must NOT match "Nref/Npar = 34.1" which also contains the text "Npar".
    m = re.search(r'S\s*=\s*[\d.]+,\s*Npar=\s*(\d+)', text)
    if m:
        stats.npar = int(m.group(1))

    # Data/parameter ratio: use PLATON's own reported "Nref/Npar = XX.X" value.
    m = re.search(r'Nref/Npar\s*=\s*([\d.]+)', text)
    if m:
        stats.data_param_ratio = float(m.group(1))

    # ── Residual density ──────────────────────────────────────────────────────
    # "# Calculated Rho(min) = -0.23, Rho(max) = 0.32 e/Ang**3 (From CIF+FCF data)"
    m = re.search(
        r'Calculated\s+Rho\(min\)\s*=\s*([+-]?[\d.]+),\s*Rho\(max\)\s*=\s*([+-]?[\d.]+)',
        text,
    )
    if m:
        stats.rho_min = float(m.group(1))
        stats.rho_max = float(m.group(2))

    # ── Completeness ──────────────────────────────────────────────────────────
    # PLATON uses two formats depending on structure type:
    #   centrosymmetric: "Ratio  =  0.988"      (single number = completeness)
    #   non-centrosymm:  "Ratio=1.79/0.99"      (multiplicity / completeness)
    # The regex handles both: the optional "X.XX/" before the completeness number.
    m = re.search(r'Expected.*?Ratio\s*=\s*(?:[\d.]+\s*/\s*)?([\d.]+)', text)
    if m:
        stats.completeness = float(m.group(1))

    # ── Resolution ───────────────────────────────────────────────────────────
    # Derived from theta_max and wavelength reported in the .chk header.
    theta_m = re.search(r'Obs in FCF.*?Th\(max\)=\s*([\d.]+)', text)
    wave_m  = re.search(r'Wavelength\s+([\d.]+)', text)
    if theta_m and wave_m:
        theta_max  = float(theta_m.group(1))
        wavelength = float(wave_m.group(1))
        stats.resolution = round(
            wavelength / (2.0 * math.sin(math.radians(theta_max))), 3)

    return stats


# ── .ckf types ────────────────────────────────────────────────────────────────

@dataclass
class ShellStats:
    """One resolution shell from Section 5 of the .ckf."""
    theta_max: float     # upper theta boundary of shell (degrees)
    sth_l: float         # sin(theta)/lambda upper boundary (Å⁻¹)
    n_reflns: int        # number of reflections in shell
    r1: float
    wr2: float
    goof: float          # S
    rs: float            # R(sigma) for this shell
    isig: float          # av(I/SigW) — the key I/σ diagnostic
    avg_i: float         # average I
    avg_sigw: float      # average weight-corrected sigma


@dataclass
class CkfStats:
    """Data extracted from a PLATON .ckf (FCF validation) file."""

    # Section 4: cumulative completeness
    completeness_acta: float | None = None   # at sin(th)/lambda = 0.600 (Acta limit)
    n_expected_acta: int | None = None
    n_measured_acta: int | None = None
    completeness_full: float | None = None   # at full theta_max
    n_expected_full: int | None = None
    n_measured_full: int | None = None

    # Section 5: shell-by-shell R and I/sigma statistics
    shells: list[ShellStats] = field(default_factory=list)
    isig_last_shell: float | None = None     # I/σ in the outermost shell (weak-data key)
    sth_l_last_shell: float | None = None    # sin(theta)/lambda of last shell

    # Intensity distribution (last section): % I > 2σ per shell
    pct_obs_by_shell: list[float] = field(default_factory=list)  # % I > 2*sig per shell
    pct_obs_last_shell: float | None = None  # % I > 2σ in outermost shell

    # Section 6: reflection summary
    n_unique_fcf: int | None = None          # unique reflections in FCF
    n_observed: int | None = None            # with I > 2σ(I)
    obs_fraction: float | None = None        # n_observed / n_unique_fcf
    n_missing_total: int | None = None
    n_missing_below_acta: int | None = None  # missing below sin(th)/lambda = 0.600
    rsig: float | None = None               # R(sig) = sum(σ(I))/sum(I)


def parse_ckf(ckf_path: Path) -> CkfStats:
    """Parse a PLATON .ckf (FCF validation) file; return populated CkfStats."""
    text = ckf_path.read_text(errors='replace')
    stats = CkfStats()

    # ── Section 4: cumulative completeness ───────────────────────────────────
    # Header: "Theta sin(th)/Lambda Complete  Expected Measured Total Missing"
    # Data rows: " 25.24     0.600     0.998         5144     5132       12"
    # Acta separator: "---------- ACTA Min. Res. ---"
    sec4 = _extract_section(text, 'Section 4', 'Section 5')
    if sec4:
        # Row at exactly sin(th)/lambda = 0.600 (Acta limit)
        m = re.search(
            r'^\s*([\d.]+)\s+0\.600\s+([\d.]+)\s+(\d+)\s+(\d+)',
            sec4, re.MULTILINE,
        )
        if m:
            stats.completeness_acta = float(m.group(2))
            stats.n_expected_acta   = int(m.group(3))
            stats.n_measured_acta   = int(m.group(4))

        # Row after the ACTA separator (full dataset completeness)
        acta_split = re.split(r'-+\s*ACTA Min\. Res\.', sec4)
        if len(acta_split) > 1:
            m = re.search(
                r'^\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(\d+)',
                acta_split[1], re.MULTILINE,
            )
            if m:
                stats.completeness_full = float(m.group(3))
                stats.n_expected_full   = int(m.group(4))
                stats.n_measured_full   = int(m.group(5))

    # ── Section 5: R-value statistics by shell ───────────────────────────────
    # Header: "Theta sin(Th)/L    #     R1    wR2      S     Rs av(I/SigW) ..."
    # Row:    " 12.38  0.302    649  0.053  0.164  1.602  0.018   9.17  29782.04  2584.27"
    sec5 = _extract_section(text, 'Section 5', 'Section 6')
    if sec5:
        row_pat = re.compile(
            r'^\s*([\d.]+)\s+([\d.]+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)'
            r'\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)',
            re.MULTILINE,
        )
        for m in row_pat.finditer(sec5):
            stats.shells.append(ShellStats(
                theta_max  = float(m.group(1)),
                sth_l      = float(m.group(2)),
                n_reflns   = int(m.group(3)),
                r1         = float(m.group(4)),
                wr2        = float(m.group(5)),
                goof       = float(m.group(6)),
                rs         = float(m.group(7)),
                isig       = float(m.group(8)),
                avg_i      = float(m.group(9)),
                avg_sigw   = float(m.group(10)),
            ))
        if stats.shells:
            stats.isig_last_shell  = stats.shells[-1].isig
            stats.sth_l_last_shell = stats.shells[-1].sth_l

        # R(sig) = sum(sig(I))/sum(I)
        m = re.search(r'R\(sig\)\s*=\s*sum\(sig\(I\)\)\s*/\s*sum\(I\)\s*=\s*([\d.]+)', sec5)
        if m:
            stats.rsig = float(m.group(1))

    # ── Section 6: reflection summary ────────────────────────────────────────
    sec6 = _extract_section(text, 'Section 6', 'Section 7')
    if not sec6:
        sec6 = _extract_section(text, 'Section 6', None)
    if sec6:
        m = re.search(r'Unique \(in FCF\)\s*\.+\s*(\d+)', sec6)
        if m:
            stats.n_unique_fcf = int(m.group(1))

        m = re.search(r'Observed \[I\s*\.gt\.\s*2\s*Sig\(I\)\]\s*\.+\s*(\d+)', sec6)
        if m:
            stats.n_observed = int(m.group(1))

        if stats.n_unique_fcf and stats.n_observed:
            stats.obs_fraction = round(stats.n_observed / stats.n_unique_fcf, 3)

        m = re.search(r'Missing \(Total\)\s*\.+\s*(\d+)', sec6)
        if m:
            stats.n_missing_total = int(m.group(1))

        # "Missing Th(Min) to STh/L=0.600   5"  — missing in the Acta-limit band
        m = re.search(r'Missing Th\(Min\) to STh/L=0\.600\s+(\d+)', sec6)
        if m:
            stats.n_missing_below_acta = int(m.group(1))

    # ── Intensity distribution ────────────────────────────────────────────────
    # "sh  st/l   Ang     #  0.25   1.0   2.0  Percent  Distr. ..."
    # " 1 0.301 1.661   644  99.1  97.8  96.6 ..."
    # The third percentage column (I > 2σ) is what we want.
    dist_m = re.search(
        r'Intensity Distribution.*?(?=\n\n|\Z)',
        text, re.DOTALL,
    )
    if dist_m:
        dist_text = dist_m.group(0)
        shell_pat = re.compile(
            r'^\s*\d+\s+[\d.]+\s+[\d.]+\s+\d+'
            r'\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)',
            re.MULTILINE,
        )
        pct_list = [float(m.group(3)) for m in shell_pat.finditer(dist_text)]
        stats.pct_obs_by_shell = pct_list
        if pct_list:
            stats.pct_obs_last_shell = pct_list[-1]

    return stats


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_section(text: str, start_marker: str,
                     end_marker: str | None) -> str | None:
    """Return the text between two section markers (exclusive)."""
    start = text.find(start_marker)
    if start == -1:
        return None
    start = text.find('\n', start) + 1  # skip the marker line itself
    if end_marker:
        end = text.find(end_marker, start)
        return text[start:end] if end != -1 else text[start:]
    return text[start:]
