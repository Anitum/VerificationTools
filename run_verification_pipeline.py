#!/usr/bin/env python3
"""
run_verification_pipeline.py

End-to-end verification pipeline:
  Step 1 — ROI Overlay   : draws ROI polygons on predicted frames (per-outlet DB)
  Step 2 — Annotation Excel : generates per-channel annotation Excel files
  Step 3 — Zip           : zips the Excel output folder

Usage:
    python3 run_verification_pipeline.py \
        --predict-dir /home/aabadmin/Refactor/runs/detect/predict64 \
        --config-dir  /home/aabadmin/Refactor/config

    # Custom output dir:
    python3 run_verification_pipeline.py \
        --predict-dir ... --config-dir ... \
        --output-dir /path/to/output
"""

import argparse
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import psycopg2
import yaml

from roi_image_plotter import load_db_config, process_frames_dir
from roi_overlay import ROIRenderer
from annotation_excel_gen import write_channel_excel, parse_folder


# ── Config discovery ───────────────────────────────────────────────────────────

def build_outlet_config_map(config_dir: Path) -> dict:
    """
    Recursively scan config_dir for *.yaml files.
    Read detection.outlet from each and return { outlet_name: yaml_path }.
    """
    outlet_map = {}
    for yaml_path in sorted(config_dir.rglob("*.yaml")):
        try:
            with open(yaml_path) as f:
                cfg = yaml.safe_load(f)
            outlet = cfg.get("detection", {}).get("outlet")
            if outlet:
                outlet_map[outlet.lower()] = yaml_path
        except Exception:
            pass  # skip unreadable / non-standard yamls
    return outlet_map


def outlet_from_folder(folder_name: str) -> str:
    """
    Extract outlet from a *_frames directory name.
    Pattern: {outlet}_{channel}_{timestamp}_frames
    """
    # Everything before the first _channel
    import re
    m = re.match(r"^(.+)_channel\d+_\d{8}T\d{6}_frames$", folder_name)
    return m.group(1).lower() if m else ""


# ── Helpers ────────────────────────────────────────────────────────────────────

def section(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def zip_directory(src_dir: Path, zip_path: Path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(src_dir.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(src_dir.parent))


# ── Step 1: ROI Overlay ────────────────────────────────────────────────────────

def run_roi_overlay(predict_dir: Path, outlet_config_map: dict, overlay_dir: Path) -> int:
    """
    For each outlet found in predict_dir, connect to its own DB and draw ROIs.
    Returns total number of *_frames directories processed.
    """
    overlay_dir.mkdir(parents=True, exist_ok=True)

    # Group frames dirs by outlet
    by_outlet = defaultdict(list)
    unmatched = []
    for d in sorted(predict_dir.iterdir()):
        if not (d.is_dir() and d.name.endswith("_frames")):
            continue
        outlet = outlet_from_folder(d.name)
        if outlet:
            by_outlet[outlet].append(d)
        else:
            unmatched.append(d.name)

    if unmatched:
        print(f"  ⚠  {len(unmatched)} dir(s) with unrecognised name pattern — skipped")

    if not by_outlet:
        print("  ERROR: No valid *_frames directories found.")
        return 0

    total = 0
    for outlet, dirs in sorted(by_outlet.items()):
        print(f"\n  Outlet: {outlet}  ({len(dirs)} clip dir(s))")

        config_path = outlet_config_map.get(outlet)
        if config_path is None:
            print(f"  ⚠  No config found for outlet '{outlet}' — skipping")
            continue

        print(f"  Config : {config_path}")
        db_config = load_db_config(str(config_path))
        print(f"  DB     : {db_config['dbname']} @ {db_config['host']}")

        try:
            conn = psycopg2.connect(**db_config)
        except Exception as e:
            print(f"  ✗ DB connection failed: {e} — skipping outlet")
            continue

        renderer  = ROIRenderer(conn)
        roi_cache = {}

        for fd in dirs:
            print(f"  ▶ {fd.name}")
            process_frames_dir(fd, renderer, roi_cache, overlay_dir)
            total += 1

        conn.close()
        print(f"  ✓ {outlet} done")

    return total


# ── Step 2: Annotation Excel ───────────────────────────────────────────────────

def run_annotation_excel(overlay_dir: Path, excel_dir: Path) -> int:
    excel_dir.mkdir(parents=True, exist_ok=True)

    by_channel = defaultdict(list)
    skipped = 0
    for folder in sorted(overlay_dir.iterdir()):
        if not folder.is_dir():
            continue
        meta = parse_folder(folder.name)
        if meta:
            by_channel[meta["channel"]].append((folder, meta))
        else:
            skipped += 1

    if not by_channel:
        print("  ERROR: No valid *_frames directories found in overlay output.")
        return 0

    total_clips = sum(len(v) for v in by_channel.values())
    print(f"  {total_clips} clips across {len(by_channel)} channel(s)"
          + (f" ({skipped} dirs skipped)" if skipped else ""))

    total_rows = 0
    for channel, clips in sorted(by_channel.items()):
        out_path = excel_dir / f"annotation_{channel}.xlsx"
        print(f"  {channel:20s}  {len(clips):3d} clip(s)  →  {out_path.name} ...", end=" ", flush=True)
        n = write_channel_excel(channel, clips, out_path)
        print(f"{n} rows")
        total_rows += n

    return total_rows


# ── Step 3: Zip ────────────────────────────────────────────────────────────────

def run_zip(excel_dir: Path, zip_path: Path):
    print(f"  Zipping {excel_dir.name} → {zip_path.name}")
    zip_directory(excel_dir, zip_path)
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  Zip size: {size_mb:.2f} MB")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="End-to-end ROI overlay → annotation Excel → zip pipeline (multi-outlet)"
    )
    parser.add_argument("--predict-dir", required=True,
                        help="Directory containing *_frames subdirs from YOLO predict")
    parser.add_argument("--config-dir",
                        default="/home/aabadmin/Refactor/config",
                        help="Root config directory (scanned recursively for outlet YAMLs). "
                             "Default: /home/aabadmin/Refactor/config")
    parser.add_argument("--output-dir",
                        default=str(Path(__file__).parent / "pipeline_output"),
                        help="Base output directory (default: ./pipeline_output)")
    parser.add_argument("--zip-name", default=None,
                        help="Zip filename (default: annotation_<timestamp>.zip)")
    args = parser.parse_args()

    predict_dir = Path(args.predict_dir)
    config_dir  = Path(args.config_dir)

    if not predict_dir.is_dir():
        print(f"ERROR: predict-dir not found: {predict_dir}")
        sys.exit(1)
    if not config_dir.is_dir():
        print(f"ERROR: config-dir not found: {config_dir}")
        sys.exit(1)

    datestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir  = Path(args.output_dir) / datestamp
    overlay_dir = output_dir / "roi_overlay"
    excel_dir   = output_dir / "annotation_excel"
    zip_name    = args.zip_name or f"annotation_{datestamp}.zip"
    zip_path    = output_dir / zip_name

    print(f"\nPipeline output : {output_dir}")
    print(f"Predict dir     : {predict_dir}")
    print(f"Config dir      : {config_dir}")

    # Discover outlet → config mapping
    outlet_config_map = build_outlet_config_map(config_dir)
    print(f"Outlets found in config dir: {sorted(outlet_config_map.keys())}")

    # ── Step 1 ──
    section("Step 1/3 — ROI Overlay")
    n_dirs = run_roi_overlay(predict_dir, outlet_config_map, overlay_dir)
    if n_dirs == 0:
        print("No directories processed. Aborting.")
        sys.exit(1)
    print(f"\n  ✓ ROI overlay complete ({n_dirs} clip dir(s)) → {overlay_dir}")

    # ── Step 2 ──
    section("Step 2/3 — Annotation Excel")
    total_rows = run_annotation_excel(overlay_dir, excel_dir)
    if total_rows == 0:
        print("No rows written. Aborting.")
        sys.exit(1)
    print(f"  ✓ Excel complete ({total_rows} total rows) → {excel_dir}")

    # ── Step 3 ──
    section("Step 3/3 — Zip")
    run_zip(excel_dir, zip_path)
    print(f"  ✓ Zip ready → {zip_path}")

    # ── Summary ──
    section("Done")
    print(f"  Clip dirs processed : {n_dirs}")
    print(f"  Total rows written  : {total_rows}")
    print(f"  Zip file            : {zip_path}")
    print(f"\n  To download, run on your local machine:")
    print(f"  scp aabadmin@<server-ip>:{zip_path} .\n")


if __name__ == "__main__":
    main()
