# Tello Drone Library

A Python library for flying a DJI Tello and working with its camera.

`tello_lib` does two things: it hands you the drone's video as ordinary OpenCV
images, and it lets you send flight commands. What happens in between is up
to you. Process the frames with OpenCV, YOLO, MediaPipe, or anything else
that takes a `numpy` array, and steer the drone with the result.

```python
from tello_lib import TelloController

with TelloController() as drone:
    drone.start_video_stream()
    drone.takeoff()

    for frame in drone.frames():            # BGR image, always the latest one
        offset = find_target(frame)         # your vision code, returns -1..1 or None
        if offset is None:
            drone.hover()
        else:
            drone.send_rc(yaw=40 * offset)  # turn towards the target
```

## Features

- **Video as `numpy` frames.** The stream is decoded in the background and
  you always get the latest image, so a slow detector never falls behind the drone.
- **Two ways to fly.** Step-by-step commands (`move`, `rotate`, `go`, `flip`)
  for scripted flights, and velocity control (`send_rc`) for control loops.
- **Telemetry.** Battery, height, attitude, speed, acceleration, temperature.
- **Safe by default.** Used as a context manager, the drone lands and the
  connection is closed when your code finishes, crashes, or is interrupted.
- **Clear errors.** Failed commands raise exceptions that say what the drone answered.
- **Small.** The only dependencies are `numpy` and `opencv-python`.

## Installation

Requires Python 3.9 or newer.

```bash
git clone https://github.com/AOShei/Tello_Drone.git
cd Tello_Drone
pip install -e .
```

## Quick start

Power on the drone, connect your computer to its Wi-Fi network
(`TELLO-XXXXXX`), and run:

```python
from tello_lib import TelloController

with TelloController() as drone:
    print(f"Battery: {drone.get_battery()}%")

    drone.takeoff()
    drone.move("forward", 50)   # cm
    drone.rotate("cw", 90)      # degrees
    drone.land()
```

To look through the camera without flying:

```python
import cv2
from tello_lib import TelloController

with TelloController() as drone:
    drone.start_video_stream()

    for frame in drone.frames():
        cv2.imshow("Tello", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
```

## Documentation

| Guide | Contents |
| --- | --- |
| [Getting started](docs/getting-started.md) | Installation, connecting, first flight, logging |
| [Video and vision](docs/video.md) | Reading frames and combining them with OpenCV, YOLO, or your own code |
| [Flight control](docs/flight-control.md) | Commands, velocity control, telemetry, error handling, safety |
| [API reference](docs/api.md) | Every class, method, and exception |
| [Troubleshooting](docs/troubleshooting.md) | Connection, video, and flight problems |

## Examples

| Script | What it does | Flies |
| --- | --- | --- |
| [basic_flight.py](examples/basic_flight.py) | Takes off, turns a full circle, lands | Yes |
| [aruco_detection.py](examples/aruco_detection.py) | Shows the video feed with ArUco markers highlighted, using OpenCV | No |
| [yolo_follow.py](examples/yolo_follow.py) | Follows a person using YOLO (needs `pip install ultralytics`) | Only with `--fly` |

## Development

The tests run against a simulated drone, so no hardware is needed. The video
tests need `ffmpeg` on the path and are skipped without it.

```bash
python -m unittest discover
```

## License

GPL-3.0, see [LICENSE](LICENSE).
