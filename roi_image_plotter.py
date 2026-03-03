#!/usr/bin/env python3
"""
ROI Image Plotter
Reads images from a predict directory, fetches ROI polygons from the DB
(configured via a YAML file), and overlays them on each image.

Directory structure expected:
    input_dir/
        {outlet}_{channel}_{timestamp}_frames/
            {outlet}_{channel}_{timestamp}_{frame_id}.jpg

Usage:
    python3 roi_image_plotter.py \
        --input-dir /home/aabadmin/Refactor/runs/detect/predict64 \
        --config /home/aabadmin/Refactor/config/a2b/a2b_semmancheri.yaml \
        --output-dir /home/aabadmin/roi_overlay_output
"""

import cv2
import psycopg2
import yaml
import re
import argparse
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, List, Optional

from roi_overlay import ROIRenderer


def load_db_config(yaml_path: str) -> Dict:
    """Parse DB connection details from a YAML config file."""
    with open(yaml_path, "r") as f:
        cfg = yaml.safe_load(f)

    db_url = cfg["database"]["url"]
    parsed = urlparse(db_url)

    return {
        "dbname": parsed.path.lstrip("/"),
        "user": parsed.username,
        "password": parsed.password,
        "host": parsed.hostname,
        "port": parsed.port or 5432,
    }


def parse_frames_dir(dir_name: str) -> Optional[Dict[str, str]]:
    """
    Extract outlet and channel_id from a *_frames directory name.
    Expected pattern: {outlet}_{channel}_{timestamp}_frames
    Example: semmancheri_channel1002_20260104T100005_frames
    """
    pattern = r"^(.+)_(channel\d+)_(\d{8}T\d{6})_frames$"
    match = re.match(pattern, dir_name)
    if not match:
        return None
    return {
        "outlet": match.group(1),
        "channel_id": match.group(2),
    }


def process_frames_dir(
    frames_dir: Path,
    renderer: ROIRenderer,
    roi_cache: Dict[str, List[Dict]],
    output_base: Path,
):
    """Overlay ROIs on all images inside a single *_frames directory."""
    meta = parse_frames_dir(frames_dir.name)
    if meta is None:
        print(f"⚠  Skipping (unrecognised dir name): {frames_dir.name}")
        return

    outlet = meta["outlet"]
    channel_id = meta["channel_id"]

    # Fetch ROIs once per channel (cache them)
    cache_key = f"{outlet}_{channel_id}"
    if cache_key not in roi_cache:
        rois = renderer.fetch_rois(channel_id, outlet)
        roi_cache[cache_key] = rois
        print(f"   Cached {len(rois)} ROI(s) for {cache_key}")
    else:
        rois = roi_cache[cache_key]

    if not rois:
        print(f"⚠  No ROIs found for {cache_key}, skipping directory.")
        return

    # Mirror the directory structure under the output base
    out_dir = output_base / frames_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)

    images = sorted(frames_dir.glob("*.jpg")) + sorted(frames_dir.glob("*.png"))
    if not images:
        print(f"⚠  No images found in {frames_dir.name}")
        return

    print(f"   Drawing ROIs on {len(images)} image(s) → {out_dir}")

    for img_path in images:
        frame = cv2.imread(str(img_path))
        if frame is None:
            print(f"   ⚠  Could not read {img_path.name}, skipping.")
            continue

        fh, fw = frame.shape[:2]
        frame = renderer.draw(frame, rois, fw, fh)

        out_path = out_dir / img_path.name
        cv2.imwrite(str(out_path), frame)

    print(f"   ✓ Done: {frames_dir.name}")


def main():
    parser = argparse.ArgumentParser(
        description="Overlay ROI polygons on predicted frames using DB config from YAML"
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing *_frames subdirectories with images",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to YAML config file (e.g. a2b_semmancheri.yaml)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: <input_dir>_roi_overlay)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"❌ Input directory not found: {input_dir}")
        return

    output_dir = Path(args.output_dir) if args.output_dir else Path(str(input_dir) + "_roi_overlay")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📂 Input : {input_dir}")
    print(f"📁 Output: {output_dir}")
    print(f"⚙  Config: {args.config}")

    db_config = load_db_config(args.config)
    print(f"🔌 Connecting to DB: {db_config['dbname']}")

    conn = psycopg2.connect(**db_config)
    print("✓ Connected")

    renderer = ROIRenderer(conn)
    roi_cache: Dict[str, List[Dict]] = {}

    frames_dirs = sorted(d for d in input_dir.iterdir() if d.is_dir() and d.name.endswith("_frames"))

    if not frames_dirs:
        print("❌ No *_frames directories found in input directory.")
        conn.close()
        return

    print(f"\n🎯 Found {len(frames_dirs)} channel frame director(ies)\n")

    for frames_dir in frames_dirs:
        print(f"▶ {frames_dir.name}")
        process_frames_dir(frames_dir, renderer, roi_cache, output_dir)

    conn.close()
    print(f"\n✅ Done! Output saved to: {output_dir}")


if __name__ == "__main__":
    main()
