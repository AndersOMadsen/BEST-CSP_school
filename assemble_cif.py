#!/usr/bin/env python3
"""
assemble_cif.py — Merge published CIF header with SHELXL refinement output.

The published CIF is the ground-truth / answer: it carries the correct experimental
metadata (radiation, wavelength, temperature, crystal description, cell s.u.'s, etc.).
The SHELXL CIF carries the refinement results for this rung (R-factors, atom
coordinates, ADPs, embedded .res and .hkl).  This module stitches them together.

PLATON requires both sets to be present and consistent to produce a full report.
"""
from __future__ import annotations
from pathlib import Path
import gemmi


# Tags that belong to SHELXL's refinement output.
# Values for these tags are taken from the SHELXL CIF, NOT the published CIF,
# so they reflect the actual rung refinement rather than the original structure.
_SHELXL_OWNED_PREFIXES: tuple[str, ...] = (
    '_atom_site',                    # fractional coordinates, occupancies, types
    '_refine',                       # R-factors, weighting, restraint counts
    '_diffrn_reflns',                # reflection statistics derived from the data
    '_diffrn_measured_fraction',     # completeness fractions (theta_full, theta_max)
                                     # SHELXL computes these from the actual HKL;
                                     # if copied from the published CIF they stay at
                                     # the original value and PLAT029 never fires
    '_reflns_',                      # merged reflection summary from the data
    '_shelx_res_file',               # embedded SHELXL .res (the model — keep as-is)
    '_shelx_hkl_file',               # embedded SHELXL .hkl (the data — keep as-is)
    '_iucr_refine',                  # IUCr refinement-specific extension tags
)


def _shelxl_owns(tag: str) -> bool:
    tl = tag.lower()
    return any(tl.startswith(p) for p in _SHELXL_OWNED_PREFIXES)


def merge_cif(published_cif: Path, shelxl_cif: Path, output_cif: Path) -> None:
    """
    Build a PLATON-ready CIF by overlaying published header metadata on top of
    SHELXL refinement output.

    Specifically:
      - Scalar pairs in published_cif that are NOT in _SHELXL_OWNED_PREFIXES
        are copied into (or overwrite) the corresponding entry in shelxl_cif.
        This brings in wavelength, temperature, crystal description, cell s.u.'s,
        cell-measurement details, absorption correction flags, etc.
      - Loops are not copied from the published CIF (they are large and belong
        to the refinement result in the SHELXL block).
      - The embedded _shelx_res_file and _shelx_hkl_file are always preserved.

    Writes the merged document to output_cif (may be the same path as shelxl_cif).
    """
    pub_doc   = gemmi.cif.read(str(published_cif))
    shelx_doc = gemmi.cif.read(str(shelxl_cif))

    # Handle CIFs with multiple data blocks (some Acta E files have several)
    try:
        pub_block = pub_doc.sole_block()
    except Exception:
        pub_block = pub_doc[0]

    try:
        shelx_block = shelx_doc.sole_block()
    except Exception:
        shelx_block = shelx_doc[0]

    # Copy scalar pairs from published → SHELXL block
    for item in pub_block:
        pair = item.pair
        if pair is None:
            continue  # skip loops
        tag, value = pair[0], pair[1]
        if _shelxl_owns(tag):
            continue  # SHELXL's own result — do not overwrite
        shelx_block.set_pair(tag, value)

    shelx_doc.write_file(str(output_cif))
