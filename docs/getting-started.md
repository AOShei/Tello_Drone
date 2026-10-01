# Getting started

## Requirements

- A DJI Tello or Tello EDU
- Python 3.9 or newer
- A computer with Wi-Fi

## Installation

```bash
git clone https://github.com/AOShei/Tello_Drone.git
cd Tello_Drone
pip install -e .
```

This installs `tello_lib` together with `numpy` and `opencv-python`.

> If you already have `opencv-contrib-python` or `opencv-python-headless`
> installed, uninstall it first. The OpenCV packages cannot be installed side
> by side.

## Connecting

1. Power on the drone and wait for its light to start blinking.
2. Connect your computer to the drone's Wi-Fi network. It is named
   `TELLO-XXXXXX`.
3. Close the Tello app if it is running on a device connected to the drone.

Check the connection without flying:

```python
from tello_lib import TelloController

with TelloController() as drone:
    print(f"Battery: {drone.get_battery()}%")
```

If this prints the battery level, everything is working. If not, see
[Troubleshooting](troubleshooting.md).

## First flight

Put the drone on a flat surface with a couple of meters of free space around
it.

```python
from tello_lib import TelloController

with TelloController() as drone:
    drone.takeoff()
    drone.move("up", 30)
    drone.rotate("cw", 360)
    drone.land()
```

## The `with` block

`with TelloController() as drone:` connects on entry. On exit it lands the
drone if it is still flying and closes the connection. This also happens when
your code raises an exception or you press Ctrl+C, which is what you want
when experimenting.

You can manage the connection yourself instead:

```python
drone = TelloController()
drone.connect()
try:
    drone.takeoff()
    ...
    drone.land()
finally:
    drone.disconnect()
```

Note that `disconnect()` does not land the drone. A Tello that stops
receiving commands lands by itself after 15 seconds.

## Logging

The library reports what it is doing through Python's `logging` module and
is silent unless you turn logging on:

```python
import logging

logging.basicConfig(level=logging.INFO)
```

Use `logging.DEBUG` to see every command sent to the drone and every
response.

## Next steps

- [Video and vision](video.md): read the camera and run your own image processing
- [Flight control](flight-control.md): the two ways to fly, telemetry, and error handling
- [API reference](api.md)
