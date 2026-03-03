# ROI Overlay Pipeline

Visualizes Region of Interest (ROI) polygons on extracted CCTV frames by fetching polygon geometry from the database and drawing them using OpenCV.

---

## Files

| File | Class / Role |
|---|---|
| `roi_image_plotter.py` | CLI entry point — orchestrates the full pipeline |
| `roi_overlay.py` | `ROIRenderer` — DB fetch + polygon drawing |
| `roi_db_checker.py` | `ROIDBChecker` — detection hit/miss counts per frame (planned integration) |

---

## Architecture

```
roi_image_plotter.py  (CLI entry point)
       │
       ├── reads YAML config → connects to PostgreSQL
       ├── scans input_dir for *_frames subdirectories
       │
       └── for each frames dir:
               └── roi_overlay.ROIRenderer
                       ├── fetch_rois()       → roi_section_polygons_geometries_<outlet>
                       ├── parse_wkt_polygon() → WKT → normalized (x, y) points
                       ├── to_pixel_coords()  → normalized → pixel coordinates
                       └── draw()             → OpenCV fillPoly + polylines on frame

roi_db_checker.ROIDBChecker  (not yet wired into plotter)
       └── fetch_roi_hits()  → detections_in_section_<outlet>
               returns: { frame_id: { "hits": X, "total": Y } }
```

---

## Usage

```bash
python3 roi_image_plotter.py \
    --input-dir /home/aabadmin/Refactor/runs/detect/predict64 \
    --config /home/aabadmin/Refactor/config/a2b/a2b_semmancheri.yaml \
    --output-dir /home/aabadmin/roi_overlay_output
```

### Arguments

| Argument | Required | Description |
|---|---|---|
| `--input-dir` | Yes | Directory containing `*_frames` subdirectories |
| `--config` | Yes | YAML config file with `database.url` |
| `--output-dir` | No | Output directory (default: `<input_dir>_roi_overlay`) |

---

## Input Directory Structure

```
input_dir/
    {outlet}_{channel}_{timestamp}_frames/
        {outlet}_{channel}_{timestamp}_{frame_id}.jpg
```

Example:
```
predict64/
    semmancheri_channel1002_20260104T100005_frames/
        semmancheri_channel1002_20260104T100005_0001.jpg
        semmancheri_channel1002_20260104T100005_0002.jpg
```

---

## YAML Config Format

```yaml
database:
  url: postgresql://user:password@host:5432/dbname
```

---

## Database Tables

### `roi_section_polygons_geometries_<outlet>`
Stores ROI polygon geometry per channel.

| Column | Description |
|---|---|
| `channel_id` | e.g. `channel1002` |
| `outlet` | e.g. `semmancheri` |
| `polygon_id` | ROI identifier |
| `geom` | PostGIS geometry (WKT POLYGON with normalized coords 0–1) |

### `detections_in_section_<outlet>` (`ROIDBChecker`)
Stores per-frame detection results with ROI classification.

| Column | Description |
|---|---|
| `channel_id` | Camera channel |
| `frame_id` | Frame number |
| `timestamp` | Detection timestamp |
| `in_geom` | Boolean — whether detection was inside the ROI |

---

## Output

Processed frames are saved mirroring the input directory structure under `--output-dir`. Each frame has:
- Filled semi-transparent yellow polygon for each ROI
- Yellow polygon border
- Label `ROI <polygon_id>` at the polygon's first vertex

---

## ROIDBChecker (Future Integration)

`roi_db_checker.py` is designed to complement the overlay by annotating frames with detection counts:

```python
checker = ROIDBChecker(conn, outlet="semmancheri")
hits = checker.fetch_roi_hits(channel_id, start_time, end_time)
# hits = { frame_id: { "hits": 3, "total": 5 } }
```

Once wired into `roi_image_plotter.py`, it could render hit counts directly on each overlaid frame.
