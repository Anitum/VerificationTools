# import psycopg2
# from psycopg2.extras import RealDictCursor
# from typing import Dict, List
# from datetime import datetime


# class ROIDBChecker:
#     """
#     Fetch ROI classification results from detections_in_section_semmancheri
#     """

#     def __init__(self, conn):
#         self.conn = conn

#     def fetch_roi_hits(
#         self,
#         channel_id: str,
#         outlet: str,
#         start_time: datetime,
#         end_time: datetime
#     ) -> Dict[int, Dict[str, int]]:
#         """
#         Returns dict: frame_id → { "hits": X, "total": Y }
#         """

#         query = """
#             SELECT frame_id, in_geom
#             FROM detections_in_section_semmancheri
#             WHERE channel_id = %s
#               AND outlet = %s
#               AND timestamp BETWEEN %s AND %s
#             ORDER BY frame_id
#         """

#         with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
#             cur.execute(query, (channel_id, outlet, start_time, end_time))
#             rows = cur.fetchall()

#         roi_by_frame: Dict[int, Dict[str, int]] = {}

#         for r in rows:
#             fid = r["frame_id"]
#             hit = r["in_geom"]

#             if fid not in roi_by_frame:
#                 roi_by_frame[fid] = {"hits": 0, "total": 0}

#             roi_by_frame[fid]["total"] += 1
#             if hit:
#                 roi_by_frame[fid]["hits"] += 1

#         return roi_by_frame
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict
from datetime import datetime


class ROIDBChecker:
    """
    Fetch ROI classification results from
    detections_in_section_<outlet>
    """

    def __init__(self, conn, outlet: str):
        # db connection passed from main script
        self.conn = conn

        # outlet comes from video file name
        self.outlet = outlet.lower()

        # build table name dynamically
        self.table_name = f"detections_in_section_{self.outlet}"
        print(self.table_name)

        # just for sanity check
        print(f"[ROI DB] Using table: {self.table_name}")

    def fetch_roi_hits(
        self,
        channel_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[int, Dict[str, int]]:
        """
        Returns:
        {
            frame_id: {
                "hits": X,
                "total": Y
            }
        }
        """

        # NOTE:
        # table name cannot be %s, so we use f-string carefully
        query = f"""
            SELECT frame_id, in_geom
            FROM {self.table_name}
            WHERE channel_id = %s
              AND timestamp BETWEEN %s AND %s
            ORDER BY frame_id
        """

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (channel_id, start_time, end_time))
            rows = cur.fetchall()

        roi_by_frame: Dict[int, Dict[str, int]] = {}

        for r in rows:
            frame_id = r["frame_id"]
            in_geom = r["in_geom"]

            if frame_id not in roi_by_frame:
                roi_by_frame[frame_id] = {
                    "hits": 0,
                    "total": 0
                }

            roi_by_frame[frame_id]["total"] += 1
            if in_geom:
                roi_by_frame[frame_id]["hits"] += 1

        return roi_by_frame
