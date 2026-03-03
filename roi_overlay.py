import cv2
import numpy as np
from typing import List, Dict


class ROIRenderer:
    """
    Handles fetching, parsing and rendering ROI polygons
    """

    def __init__(self, conn):
        """
        Args:
            conn: psycopg2 database connection
        """
        self.conn = conn

    # ---------------------------
    # DB FETCH
    # ---------------------------
    # def fetch_rois(self, channel_id: str, outlet: str) -> List[Dict]:
    #     outlet = outlet.lower()
    #     table_name = f"roi_section_polygons_geometries_{outlet}"
    #     query = f"""
    #         SELECT polygon_id,
    #                ST_AsText(geom) AS wkt
    #         FROM {table_name}
    #         WHERE channel_id = %s
    #           AND outlet = %s
    #         ORDER BY polygon_id
    #     """

    #     from psycopg2.extras import RealDictCursor
    #     with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
    #         cur.execute(query, (channel_id, outlet))
    #         rois = cur.fetchall()

    #     print(f"✓ Loaded {len(rois)} ROI polygons")
    #     return rois
    def fetch_rois(self, channel_id: str, outlet: str) -> List[Dict]:
        outlet = outlet.lower()

        # Normalize channel_id for ROI DB
        if not channel_id.startswith("channel"):
            channel_id = f"channel{channel_id}"

        table_name = f"roi_section_polygons_geometries_{outlet}"

        query = f"""
            SELECT polygon_id,
                ST_AsText(geom) AS wkt
            FROM {table_name}
            WHERE channel_id = %s
            AND outlet = %s
            ORDER BY polygon_id
        """

        from psycopg2.extras import RealDictCursor
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (channel_id, outlet))
            rois = cur.fetchall()

        print(f"✓ Loaded {len(rois)} ROI polygons")
        return rois

    # ---------------------------
    # GEOMETRY PARSING
    # ---------------------------
    @staticmethod
    def parse_wkt_polygon(wkt: str) -> List[tuple]:
        """
        Convert WKT POLYGON to list of normalized (x, y)
        """
        coords = wkt.replace("POLYGON((", "").replace("))", "")
        points = []

        for pair in coords.split(","):
            x, y = pair.strip().split()
            points.append((float(x), float(y)))

        return points

    @staticmethod
    def to_pixel_coords(
        points_norm: List[tuple],
        frame_width: int,
        frame_height: int
    ) -> np.ndarray:
        """
        Convert normalized points to pixel coordinates
        """
        pts = [
            (int(x * frame_width), int(y * frame_height))
            for x, y in points_norm
        ]
        return np.array(pts, dtype=np.int32)

    # ---------------------------
    # DRAWING
    # ---------------------------
    def draw(
        self,
        frame: np.ndarray,
        rois: List[Dict],
        frame_width: int,
        frame_height: int,
        alpha: float = 0.25
    ) -> np.ndarray:
        """
        Draw ROI polygons on frame
        """
        overlay = frame.copy()

        for roi in rois:
            pts_norm = self.parse_wkt_polygon(roi["wkt"])
            pts_px = self.to_pixel_coords(
                pts_norm, frame_width, frame_height
            )

            # Filled polygon (transparent)
            cv2.fillPoly(overlay, [pts_px], (0, 255, 255))

            # Border
            cv2.polylines(
                frame, [pts_px],
                isClosed=True,
                color=(0, 255, 255),
                thickness=2
            )

            # Label
            x, y = pts_px[0]
            cv2.putText(
                frame,
                f"ROI {roi['polygon_id']}",
                (x, y - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2
            )

        # Blend overlay
        frame[:] = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
        return frame
