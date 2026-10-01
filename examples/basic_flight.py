#!/usr/bin/env python3
"""Take off, turn a full circle, and land.

Connect to the drone's Wi-Fi network first, and make sure it has room to fly.
"""
import logging
import time

from tello_lib import TelloController, TelloError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def main():
    try:
        # Leaving the with block lands the drone, also on Ctrl+C or an error
        with TelloController() as drone:
            battery = drone.get_battery()
            logger.info(f"Battery level: {battery}%")
            if battery < 10:
                logger.error("Battery too low for flight!")
                return

            logger.info("Taking off...")
            drone.takeoff()
            time.sleep(3)  # Stabilize after takeoff

            logger.info("Rotating...")
            drone.rotate("cw", 360)
            drone.log_status()

            logger.info("Landing...")
            drone.land()
    except TelloError as e:
        logger.error(f"Flight failed: {e}")
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")


if __name__ == "__main__":
    main()
