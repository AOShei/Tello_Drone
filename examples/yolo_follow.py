#!/usr/bin/env python3
"""Follow a person with YOLO.

The drone turns and climbs to keep the largest detected person centered in
the image, and moves forward or back to keep them at a constant apparent size.

YOLO is not part of tello_lib. This script shows how to combine the two, and
needs ultralytics installed:

    pip install ultralytics

By default the drone stays on the ground and only shows what it would do.
Check that the detections and the printed commands look right, then run with
--fly in an open space. Press 'q' in the video window to land and quit.
"""
import argparse
import logging

import cv2
from ultralytics import YOLO

from tello_lib import TelloController, TelloError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

WINDOW = 'Tello YOLO Follow'
PERSON_CLASS = 0  # COCO class id

# Fraction of the image height the person should fill. Smaller keeps the
# drone further away.
TARGET_HEIGHT = 0.5

# Proportional gains, from normalized image error to rc value (-100..100)
YAW_GAIN = 60
UP_DOWN_GAIN = 40
FORWARD_GAIN = 80
MAX_RC = 35  # Cap the speed, this is a demo, not a race


def clamp(value: float) -> int:
    return int(max(-MAX_RC, min(MAX_RC, value)))


def follow_command(box, frame_width: int, frame_height: int):
    """Compute (forward_back, up_down, yaw) rc values from a bounding box

    Args:
        box: (x1, y1, x2, y2) of the target in pixels
    """
    x1, y1, x2, y2 = box
    # Offsets of the box center from the image center, -1..1
    x_error = ((x1 + x2) / 2 - frame_width / 2) / (frame_width / 2)
    y_error = ((y1 + y2) / 2 - frame_height / 2) / (frame_height / 2)
    size_error = TARGET_HEIGHT - (y2 - y1) / frame_height

    yaw = clamp(YAW_GAIN * x_error)             # Target to the right: turn clockwise
    up_down = clamp(-UP_DOWN_GAIN * y_error)    # Target above center (y grows downward): climb
    forward_back = clamp(FORWARD_GAIN * size_error)  # Target looks small: approach
    return forward_back, up_down, yaw


def largest_person(result):
    """Return the (x1, y1, x2, y2) box of the largest detection, None if there is none"""
    boxes = result.boxes.xyxy.tolist()
    if not boxes:
        return None
    return max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--fly', action='store_true', help="take off and follow (default: stay on the ground)")
    parser.add_argument('--model', default='yolo11n.pt', help="YOLO model to use (default: %(default)s)")
    args = parser.parse_args()

    model = YOLO(args.model)

    try:
        with TelloController() as drone:
            logger.info(f"Battery level: {drone.get_battery()}%")
            drone.start_video_stream()

            if args.fly:
                logger.info("Taking off...")
                drone.takeoff()

            try:
                # frames() skips the frames that arrive during inference, so
                # the control loop always acts on the latest image
                for frame in drone.frames():
                    result = model(frame, classes=[PERSON_CLASS], verbose=False)[0]
                    box = largest_person(result)

                    if box is not None:
                        height, width = frame.shape[:2]
                        forward_back, up_down, yaw = follow_command(box, width, height)
                    else:
                        forward_back, up_down, yaw = 0, 0, 0  # Nobody in view: hover

                    if args.fly:
                        drone.send_rc(0, forward_back, up_down, yaw)

                    annotated = result.plot()
                    cv2.putText(
                        annotated, f"fwd:{forward_back} up:{up_down} yaw:{yaw}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
                    )
                    cv2.imshow(WINDOW, annotated)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
            finally:
                if drone.is_flying:
                    drone.hover()
            # Leaving the with block lands the drone
    except TelloError as e:
        logger.error(f"An error occurred: {e}")
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
