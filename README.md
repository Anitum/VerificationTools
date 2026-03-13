# Verification Tool

End-to-end pipeline for verifying YOLO detection outputs on CCTV footage.
Draws ROI overlays on predicted frames and generates per-channel annotation Excel files for human review.

---

## Pipeline Overview

```
YOLO predict output (*_frames dirs)
        │
        ▼
[Step 1] roi_image_plotter.py   — fetches ROI polygons from DB, draws overlays on frames
        │
        ▼
[Step 2] annotation_excel_gen.py — picks representative frame per 5s bucket,
        │                          embeds thumbnails into per-channel Excel sheets
        ▼
[Step 3] Zip                    — zips the annotation_excel/ folder
        │
        ▼
  annotation_<timestamp>.zip   → download via scp → send to annotation team
```

---

## Quick Start (Automated Pipeline)

Runs all three steps in sequence. Supports **multiple outlets with different DBs** — configs are auto-discovered from the config directory.

```bash
python3 run_verification_pipeline.py \
    --predict-dir /home/aabadmin/Refactor/runs/detect/predict64 \
    --config-dir  /home/aabadmin/Refactor/config
```

### Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `--predict-dir` | Yes | — | Directory containing `*_frames` subdirs from YOLO predict |
| `--config-dir` | No | `/home/aabadmin/Refactor/config` | Root config directory (scanned recursively for outlet YAMLs) |
| `--output-dir` | No | `./pipeline_output` | Base output directory |
| `--zip-name` | No | `annotation_<timestamp>.zip` | Custom zip filename |

### Output structure

```
pipeline_output/
└── <YYYYMMDD_HHMMSS>/
    ├── roi_overlay/               ← Step 1 output
    │   └── <outlet>_<channel>_<ts>_frames/
    │       └── *.jpg              (ROI polygons drawn on frames)
    ├── annotation_excel/          ← Step 2 output
    │   ├── annotation_channel1002.xlsx
    │   └── annotation_channel1202.xlsx
    └── annotation_<timestamp>.zip ← Step 3 output (send to annotation team)
```

Each run creates a new timestamped subfolder — previous runs are never overwritten.

### Download zip from server

```bash
scp aabadmin@<server-ip>:/path/to/pipeline_output/<timestamp>/annotation_<timestamp>.zip .
```

---

## Multi-Outlet Support

The pipeline auto-discovers configs by scanning `--config-dir` recursively for `*.yaml` files and reading the `detection.outlet` field from each. Each outlet gets its own DB connection.

Config directory structure:
```
/home/aabadmin/Refactor/config/
├── a2b/
│   ├── a2b_semmancheri.yaml    → outlet: semmancheri
│   ├── a2b_annanagar.yaml      → outlet: annanagar
│   └── ...
├── calb/
│   └── calb_kathipara.yaml     → outlet: kathipara
└── jk/
    └── jk_nungambakkam.yaml    → outlet: nungambakkam
```

The outlet name is parsed from each `*_frames` folder name (`{outlet}_{channel}_{timestamp}_frames`) and matched to the correct config automatically.

---

## Running Steps Individually

### Step 1 — ROI Overlay

```bash
python3 roi_image_plotter.py \
    --input-dir  /home/aabadmin/Refactor/runs/detect/predict64 \
    --config     /home/aabadmin/Refactor/config/a2b/a2b_semmancheri.yaml \
    --output-dir /home/aabadmin/roi_overlay_output
```

See `docs/roi_overlay_pipeline.md` for full details.

### Step 2 — Annotation Excel

```bash
python3 annotation_excel_gen.py \
    --input-dir  /home/aabadmin/roi_overlay_output \
    --output-dir /home/aabadmin/annotation_excel
```

See `docs/annotation_excel_gen.md` for full details.

---

## Files

| File | Role |
|---|---|
| `run_verification_pipeline.py` | Automated end-to-end pipeline (Steps 1–3) |
| `roi_image_plotter.py` | Step 1 CLI — ROI overlay on frames |
| `roi_overlay.py` | `ROIRenderer` — DB fetch + polygon drawing |
| `roi_db_checker.py` | `ROIDBChecker` — detection hit/miss counts (future) |
| `annotation_excel_gen.py` | Step 2 CLI — annotation Excel generation |
| `verify_timestamps.py` | OCR-based T1 vs T2 timestamp discrepancy checker |
| `docs/roi_overlay_pipeline.md` | Detailed docs for Step 1 |
| `docs/annotation_excel_gen.md` | Detailed docs for Step 2 |

---

## Prerequisites

```bash
pip install opencv-python psycopg2-binary pyyaml openpyxl pillow
sudo apt install tesseract-ocr   # only needed for verify_timestamps.py
pip install pytesseract           # only needed for verify_timestamps.py
```

---

## Timestamp Reference

| Label | Source | Timezone |
|---|---|---|
| T1 | Burned into frame by camera OSD | IST (UTC+5:30) |
| T2 | Computed from clip filename + frame_id × 1.5s | UTC |
| T3 | DB / processing time (`ts_5s` column in headcount CSV) | UTC |

T1 will appear ~5h 30min ahead of T2 — this is expected. Use `verify_timestamps.py` to measure the T1–T2 offset.
