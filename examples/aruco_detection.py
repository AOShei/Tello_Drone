#!/usr/bin/env python3
"""Show the drone's video feed and highlight ArUco markers.

The drone stays on the ground, so this is a safe way to check the video
stream. Press 'q' in the video window to quit.
"""
import logging

import cv2
import numpy as np

from tello_lib import TelloController, TelloError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

WINDOW = 'Tello Video Feed'


def main():
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
    detector = cv2.aruco.ArucoDetector(aruco_dict, cv2.aruco.DetectorParameters())
    visible_ids = set()

    try:
        with TelloController() as drone:
            logger.info("Starting video stream...")
            drone.start_video_stream()

            for frame in drone.frames():
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                corners, ids, _ = detector.detectMarkers(gray)

                if ids is not None:
                    cv2.aruco.drawDetectedMarkers(frame, corners, ids)
                    # Log markers when they come into view
                    for marker_id, corner in zip(ids.flatten(), corners):
                        if marker_id not in visible_ids:
                            center = np.mean(corner[0], axis=0)
                            logger.info(f"Detected marker {marker_id} at ({center[0]:.0f}, {center[1]:.0f})")
                visible_ids = set(ids.flatten()) if ids is not None else set()

                cv2.imshow(WINDOW, frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
    except TelloError as e:
        logger.error(f"An error occurred: {e}")
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
