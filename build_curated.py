#!/usr/bin/env python3
"""
build_curated.py  —  populate Streamlit_app/curated/ from Pipeline rungs.

USAGE
-----
Step 1 — generate the selection table:
    python build_curated.py

    Scans Pipeline/structures.yaml and all rung directories, writes
    curated_selection.csv with one row per available rung.  Open the CSV
    in Excel/Numbers, mark 'include = yes' for the rungs you want, fill in
    the five user columns, then run step 2.

Step 2 — apply the selection:
    python build_curated.py --apply

    Reads curated_selection.csv, copies CIF/FCF files into
    Streamlit_app/curated/, creates stub teaching notes, and writes a
    complete Streamlit_app/curated/metadata.json.

USER COLUMNS (you fill these in before --apply)
---------------
include            yes  to include this rung; anything else = skip
label              unique slug, e.g. hb8120_ms  (no spaces)
title              non-revealing title students see, e.g. "Case 04"
pathology_category short phrase for the hint expander, e.g. "Missed symmetry"
assigned_groups    comma-separated group numbers, e.g.  1,3  or  all

AUTO-POPULATED (pre-filled by the script, do not edit)
---------------
structure_id, rung_tag, rung_type, source_route, space_group, radiation,
R1, wR2, alerts_A, alerts_B, alerts_C, catastrophic, cif_path, fcf_available,
suggested_label
"""

import argparse
import csv
import json
import re
import shutil
import sys
from pathlib import Path

import yaml

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT          = Path(__file__).parent
PIPELINE_DIR  = ROOT / "Pipeline"
DATA_DIR      = PIPELINE_DIR / "Good_Structures_and_data"
STRUCTURES_YML = PIPELINE_DIR / "structures.yaml"
CURATED_DIR   = ROOT / "Streamlit_app" / "curated"
SELECTION_CSV = ROOT / "curated_selection.csv"

# ── Mappings ───────────────────────────────────────────────────────────────────
_OP_TO_PATHOLOGY = {
    "reference":                   "Reference (no degradation)",
    "truncate_resolution":         "Data quality — low resolution",
    "reduce_completeness_unique":  "Data quality — incomplete data",
    "remove_cone":                 "Data quality — systematic gaps (3DED geometry)",
    "remove_wedge":                "Data quality — low-angle wedge missing",
    "simulate_weak_data":          "Data quality — weak data",
    "inject_absorption_error":     "Data quality — absorption error",
    "ms":                          "Missed symmetry",
    "wa":                          "Atom misassignment",
    "ma":                          "Missing atoms",
}

_OP_TO_SOURCE_ROUTE = {
    "reference":                   "synthetic-degraded",
    "truncate_resolution":         "synthetic-degraded",
    "reduce_completeness_unique":  "synthetic-degraded",
    "remove_cone":                 "synthetic-degraded",
    "remove_wedge":                "synthetic-degraded",
    "simulate_weak_data":          "synthetic-degraded",
    "inject_absorption_error":     "synthetic-degraded",
    "ms":                          "synthetic-wrong-symmetry",
    "wa":                          "synthetic-wrong-atom",
    "ma":                          "synthetic-missing-atoms",
}

_OP_TO_TYPE = {
    "reference":                   "data-degradation",
    "truncate_resolution":         "data-degradation",
    "reduce_completeness_unique":  "data-degradation",
    "remove_cone":                 "data-degradation",
    "remove_wedge":                "data-degradation",
    "simulate_weak_data":          "data-degradation",
    "inject_absorption_error":     "data-degradation",
    "ms":                          "missed-symmetry",
    "wa":                          "wrong-atom",
    "ma":                          "missing-atoms",
}

USER_COLUMNS  = ["include", "label", "title", "pathology_category", "assigned_groups"]
AUTO_COLUMNS  = [
    "structure_id", "rung_tag", "rung_type", "source_route",
    "space_group", "radiation",
    "R1", "wR2", "Rint", "completeness",
    "alerts_A", "alerts_B", "alerts_C", "catastrophic",
    "cif_path", "fcf_available", "suggested_label",
]
ALL_COLUMNS   = USER_COLUMNS + AUTO_COLUMNS


# ── Helpers ────────────────────────────────────────────────────────────────────

def _suggested_label(struct_id: str, rung_tag: str) -> str:
    """Build a concise slug from the structure id and rung tag."""
    # Strip leading digits from rung tag: "01_res_1p0" → "res1p0"
    short = re.sub(r"^\d+_", "", rung_tag).replace("_", "")
    return f"{struct_id}_{short}"


def _load_summary(struct_dir: Path) -> dict[str, dict]:
    """Return {rung_tag: {R1, wR2, alerts_A, ...}} from ladder/summary.csv."""
    csv_path = struct_dir / "ladder" / "summary.csv"
    if not csv_path.exists():
        return {}
    result = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tag = row.get("rung", "").strip()
            if tag:
                result[tag] = row
    return result


def _rung_files(struct_dir: Path, rung_tag: str, shelx_name: str):
    """Return (cif_path, fcf_path) for a rung, or None if not found."""
    rung_dir = struct_dir / "ladder" / f"rung_{rung_tag}"
    if not rung_dir.exists():
        return None, None
    cif = rung_dir / f"{shelx_name}.cif"
    fcf = rung_dir / f"{shelx_name}.fcf"
    return (cif if cif.exists() else None,
            fcf if fcf.exists() else None)


# ── Mode 1: generate CSV ───────────────────────────────────────────────────────

def generate_csv():
    with open(STRUCTURES_YML, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Load any existing user-filled values so re-runs don't wipe them
    existing: dict[tuple, dict] = {}
    if SELECTION_CSV.exists():
        with open(SELECTION_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = (row["structure_id"], row["rung_tag"])
                existing[key] = {c: row.get(c, "") for c in USER_COLUMNS}

    rows = []
    for struct in config["structures"]:
        sid        = struct["id"]
        shelx      = struct.get("shelx_name", "I")
        sg         = struct.get("space_group", "")
        rad        = struct.get("radiation", "")
        struct_dir = DATA_DIR / struct["path"].split("/", 1)[-1]
        summary    = _load_summary(struct_dir)

        def _make_row(tag, op):
            cif_path, fcf_path = _rung_files(struct_dir, tag, shelx)
            stats = summary.get(tag, {})
            rel_cif = str(cif_path.relative_to(ROOT)) if cif_path else ""
            prev = existing.get((sid, tag), {})
            return {
                "include":           prev.get("include", ""),
                "label":             prev.get("label", ""),
                "title":             prev.get("title", ""),
                "pathology_category": prev.get("pathology_category", "") or _OP_TO_PATHOLOGY.get(op, ""),
                "assigned_groups":   prev.get("assigned_groups", ""),
                "structure_id":      sid,
                "rung_tag":          tag,
                "rung_type":         _OP_TO_TYPE.get(op, ""),
                "source_route":      _OP_TO_SOURCE_ROUTE.get(op, ""),
                "space_group":       sg,
                "radiation":         rad,
                "R1":                stats.get("R1", ""),
                "wR2":               stats.get("wR2", ""),
                "Rint":              f"{float(stats['rint'])*100:.1f}%" if stats.get("rint") else "",
                "completeness":      stats.get("completeness", ""),
                "alerts_A":          stats.get("alerts_A", ""),
                "alerts_B":          stats.get("alerts_B", ""),
                "alerts_C":          stats.get("alerts_C", ""),
                "catastrophic":      stats.get("catastrophic", ""),
                "cif_path":          rel_cif,
                "fcf_available":     "yes" if fcf_path else "no",
                "suggested_label":   _suggested_label(sid, tag),
            }

        # Regular degradation rungs
        for rung in struct.get("rungs", []):
            tag = rung["tag"]
            op  = rung["op"]
            row = _make_row(tag, op)
            if row["cif_path"]:   # only include if the rung actually ran
                rows.append(row)

        # Model-error rungs
        for me_key, me_op in [("ms_rung", "ms"), ("wa_rung", "wa"), ("ma_rung", "ma")]:
            me = struct.get(me_key, {})
            if me.get("enabled"):
                row = _make_row(me_op, me_op)
                if row["cif_path"]:
                    rows.append(row)

    with open(SELECTION_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ALL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Written {len(rows)} rows to {SELECTION_CSV}")
    print()
    print("Next steps:")
    print("  1. Open curated_selection.csv in Excel or Numbers")
    print("  2. Set  include = yes  for the rungs you want")
    print("  3. Fill in: label, title, pathology_category, assigned_groups")
    print("     (suggested_label is a starting point — copy it to label and edit)")
    print("  4. Run:  python build_curated.py --apply")


# ── Mode 2: apply selection ────────────────────────────────────────────────────

def apply_selection():
    if not SELECTION_CSV.exists():
        sys.exit(f"ERROR: {SELECTION_CSV} not found. Run without --apply first.")

    with open(STRUCTURES_YML, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    shelx_map = {s["id"]: s.get("shelx_name", "I") for s in config["structures"]}

    # Read CSV
    with open(SELECTION_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    selected = [r for r in rows if r.get("include", "").strip().lower() == "yes"]
    if not selected:
        sys.exit("No rows marked 'include = yes'. Nothing to do.")

    # Validate required user fields
    errors = []
    for r in selected:
        sid = r["structure_id"]
        for col in ["label", "title", "pathology_category"]:
            if not r.get(col, "").strip():
                errors.append(f"  Row {r['structure_id']}/{r['rung_tag']}: '{col}' is empty")
        # assigned_groups may be empty — that means reserve (instructor view only)
    if errors:
        sys.exit("Validation errors — fix these in the CSV before applying:\n" + "\n".join(errors))

    # Check for duplicate labels
    labels = [r["label"].strip() for r in selected]
    dupes = {l for l in labels if labels.count(l) > 1}
    if dupes:
        sys.exit(f"Duplicate labels: {dupes}. Each label must be unique.")

    # Prepare output dirs
    (CURATED_DIR / "cif").mkdir(parents=True, exist_ok=True)
    (CURATED_DIR / "fcf").mkdir(parents=True, exist_ok=True)
    (CURATED_DIR / "teaching_notes").mkdir(parents=True, exist_ok=True)

    metadata = []
    for r in selected:
        sid   = r["structure_id"].strip()
        tag   = r["rung_tag"].strip()
        label = r["label"].strip()
        shelx = shelx_map.get(sid, "I")

        # Locate source files
        src_cif = Path(r["cif_path"].strip()) if r.get("cif_path", "").strip() else None
        if not src_cif or not src_cif.exists():
            print(f"  WARNING: CIF not found for {sid}/{tag} — skipping")
            continue

        # Derive FCF path from CIF path (same dir, different extension)
        src_fcf = src_cif.with_suffix(".fcf")
        has_fcf = src_fcf.exists()

        # Copy files
        dst_cif = CURATED_DIR / "cif" / f"{label}.cif"
        shutil.copy2(src_cif, dst_cif)
        print(f"  Copied CIF  → curated/cif/{label}.cif")

        dst_fcf_rel = None
        if has_fcf:
            dst_fcf = CURATED_DIR / "fcf" / f"{label}.fcf"
            shutil.copy2(src_fcf, dst_fcf)
            dst_fcf_rel = f"fcf/{label}.fcf"
            print(f"  Copied FCF  → curated/fcf/{label}.fcf")

        # Create stub teaching note
        note_path = CURATED_DIR / "teaching_notes" / f"{label}.md"
        if not note_path.exists():
            note_path.write_text(
                f"# Teaching note — {label}\n\n"
                f"TODO: instructor writes the teaching note for {label} here.\n\n"
                f"This file is a stub. Replace it with the real teaching note before the course.\n",
                encoding="utf-8",
            )
            print(f"  Created stub → curated/teaching_notes/{label}.md")
        else:
            print(f"  Kept existing → curated/teaching_notes/{label}.md")

        # Parse assigned_groups
        ag_raw = r["assigned_groups"].strip().lower()
        if ag_raw in ("all", "1,2,3,4,5,6", "1-6"):
            assigned_groups = [1, 2, 3, 4, 5, 6]
        else:
            assigned_groups = [int(x.strip()) for x in ag_raw.split(",") if x.strip().isdigit()]

        # Build metadata record
        record = {
            "label":              label,
            "title":              r["title"].strip(),
            "pathology_category": r["pathology_category"].strip(),
            "teaching_note_file": f"teaching_notes/{label}.md",
            "source_route":       r.get("source_route", "").strip(),
            "citation":           r.get("citation", "").strip() or None,
            "doi":                r.get("doi", "").strip() or None,
            "deposited_id":       r.get("deposited_id", "").strip() or None,
            "cif_file":           f"cif/{label}.cif",
            "fcf_file":           dst_fcf_rel,
            "sf_report_file":     None,
            "assigned_groups":    assigned_groups,
        }
        metadata.append(record)

    # Write metadata.json
    meta_path = CURATED_DIR / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print()
    print(f"Written {len(metadata)} records to {meta_path}")
    print()
    print("Done. Next steps:")
    print("  1. Write teaching notes in Streamlit_app/curated/teaching_notes/")
    print("  2. Restart the Streamlit app and verify in the Curated tab")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Apply curated_selection.csv (copy files, write metadata.json)")
    args = parser.parse_args()

    if args.apply:
        apply_selection()
    else:
        generate_csv()
