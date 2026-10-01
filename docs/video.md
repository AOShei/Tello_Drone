# Video and vision

`tello_lib` does not do any image processing itself. It gives you frames,
you decide what to do with them. This guide covers reading the video and
shows how to connect it to OpenCV, YOLO, or your own code.

## Reading frames

Turn the camera on with `start_video_stream()`. It returns once the stream
is stable, which takes a few seconds.

```python
from tello_lib import TelloController

with TelloController() as drone:
    drone.start_video_stream()
    frame = drone.get_frame()
    print(frame.shape)   # (720, 960, 3)
```

A frame is a `numpy` array in BGR channel order, the format OpenCV uses.
Every frame you receive is your own copy, so you can draw on it or modify it
freely.

There are three ways to get frames. Pick the one that fits your program.

### `frames()`: a loop over new frames

```python
for frame in drone.frames():
    process(frame)
```

This is the right choice for most vision code. Each frame is delivered at
most once, and the loop waits when there is no new frame yet.

If the loop body takes longer than the time between frames (the camera
produces about 30 a second), the frames that arrived in the meantime are
skipped and the next iteration gets the most recent one. A detector running
at 10 frames a second therefore sees the world as it is now, not as it was
when a queue started filling up. This matters when steering the drone from
what it sees.

The loop ends when the video stream is stopped. If no frame arrives for
`timeout` seconds (5 by default) it raises `VideoStreamError`.

### `get_frame()`: the latest frame, right now

```python
frame = drone.get_frame()
```

Returns immediately with the latest frame, or `None` if there is none yet.
Calling it twice in quick succession can return the same image. Use it when
your program has its own loop and timing, for example a GUI.

### A callback

```python
def on_frame(frame):
    ...

drone.start_video_stream(frame_callback=on_frame)
```

The callback is called for every decoded frame, on the video thread. While
it runs, no new frames are decoded, so keep it short. Use this when you must
see every single frame, for example to record the video.

## Displaying video

```python
import cv2
from tello_lib import TelloController

with TelloController() as drone:
    drone.start_video_stream()

    for frame in drone.frames():
        cv2.imshow("Tello", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cv2.destroyAllWindows()
```

Call `cv2.imshow` and `cv2.waitKey` from the main thread. On some platforms
OpenCV windows do not work from other threads.

## Combining with a vision library

Every example below has the same shape:

1. Take a frame.
2. Find something in it.
3. Turn what you found into a command.

### OpenCV: follow a colored object

This turns the drone towards the largest blue object in view. It uses only
OpenCV, which is installed with the library.

```python
import cv2
import numpy as np
from tello_lib import TelloController

LOWER_BLUE = np.array([100, 150, 50])
UPPER_BLUE = np.array([130, 255, 255])

with TelloController() as drone:
    drone.start_video_stream()
    drone.takeoff()

    for frame in drone.frames():
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, LOWER_BLUE, UPPER_BLUE)
        moments = cv2.moments(mask)

        if moments["m00"] < 50_000:        # Not enough blue in view
            drone.hover()
        else:
            center_x = moments["m10"] / moments["m00"]
            width = frame.shape[1]
            offset = (center_x - width / 2) / (width / 2)   # -1 (left) to 1 (right)
            drone.send_rc(yaw=50 * offset)

        cv2.imshow("Tello", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
```

### OpenCV: ArUco markers

```python
detector = cv2.aruco.ArucoDetector(
    cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250),
    cv2.aruco.DetectorParameters(),
)

for frame in drone.frames():
    corners, ids, _ = detector.detectMarkers(frame)
    if ids is not None:
        print("Markers in view:", ids.flatten())
```

See [examples/aruco_detection.py](../examples/aruco_detection.py) for the
full program.

### YOLO

YOLO is not a dependency of this library. Install it separately:

```bash
pip install ultralytics
```

Frames can be passed to a model as they are:

```python
from ultralytics import YOLO
from tello_lib import TelloController

model = YOLO("yolo11n.pt")

with TelloController() as drone:
    drone.start_video_stream()

    for frame in drone.frames():
        result = model(frame, verbose=False)[0]
        for box in result.boxes:
            name = result.names[int(box.cls)]
            print(name, float(box.conf), box.xyxy[0].tolist())
```

[examples/yolo_follow.py](../examples/yolo_follow.py) builds on this to make
the drone follow a person.

### Other libraries

Anything that accepts an image as a `numpy` array works the same way. Two
things to check in the documentation of the library you use:

- **Channel order.** Frames are BGR. If the library expects RGB, convert
  first: `rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)`.
- **Size.** Frames are 960x720. Resize with `cv2.resize` if the model needs
  another size and does not do it for you.

## From detection to motion

To steer the drone from an image, convert the position of the target into a
number between -1 and 1 and scale it into a velocity for `send_rc()`:

```python
height, width = frame.shape[:2]
x1, y1, x2, y2 = box                      # target bounding box in pixels

x_error = ((x1 + x2) / 2 - width / 2) / (width / 2)      # -1 left .. 1 right
y_error = ((y1 + y2) / 2 - height / 2) / (height / 2)    # -1 top .. 1 bottom

drone.send_rc(
    yaw=50 * x_error,         # target to the right: turn clockwise
    up_down=-40 * y_error,    # target above the center: climb
)
```

Things worth knowing when you tune this:

- Start with small gains and a low cap on the values. A Tello at `rc` value
  100 is fast indoors.
- Call `drone.hover()` when the target is lost. Otherwise the drone keeps
  flying at the last velocity you sent.
- Test on the ground first. Print or draw the commands instead of sending
  them and check that they point the right way. The YOLO example does this
  unless it is started with `--fly`.

See [Flight control](flight-control.md) for more on `send_rc()`.

## Stopping the video

```python
drone.stop_video_stream()
```

Leaving the `with` block or calling `disconnect()` does this for you.
