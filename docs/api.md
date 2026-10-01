# API reference

Everything listed here can be imported from `tello_lib`:

```python
from tello_lib import TelloController, DroneState, DroneStatus, TelloError
```

- [TelloController](#tellocontroller)
- [DroneStatus](#dronestatus)
- [DroneState](#dronestate)
- [Exceptions](#exceptions)

## TelloController

```python
TelloController(host='192.168.10.1', *, command_port=8889,
                local_command_port=8889, status_port=8890, video_port=11111)
```

The defaults match a Tello in its factory configuration, so
`TelloController()` is normally all you need.

| Argument | Description |
| --- | --- |
| `host` | IP address of the drone |
| `command_port` | UDP port the drone listens on for commands |
| `local_command_port` | Local UDP port commands are sent from |
| `status_port` | Local UDP port the drone sends telemetry to |
| `video_port` | Local UDP port the drone sends video to |

Creating a controller does not open any connection. Use it as a context
manager (`with TelloController() as drone:`) to connect on entry and to land
and disconnect on exit, or call `connect()` and `disconnect()` yourself.

### Connection

#### `connect()`

Connects to the drone and puts it in SDK mode. Does nothing if already
connected.

Raises `DroneConnectionError` if the drone does not answer or a local port
is already in use.

#### `disconnect()`

Stops the video stream and releases all resources. Does **not** land the
drone. The controller can be connected again afterwards.

#### `state`

The current [`DroneState`](#dronestate).

#### `is_flying`

`True` while the drone is in the air.

### Flight

All methods in this section except `send_rc()` and `hover()` block until the
drone has answered.

#### `takeoff()`

Takes off and hovers. Raises `TakeoffError` if the drone is not connected,
is already flying, or did not take off.

#### `land()`

Lands the drone. Raises `LandingError` if the landing could not be
confirmed.

#### `emergency()`

Stops all motors immediately. The drone drops.

#### `move(direction, distance)`

Moves in a straight line.

| Argument | Description |
| --- | --- |
| `direction` | `'up'`, `'down'`, `'left'`, `'right'`, `'forward'` or `'back'` |
| `distance` | Distance in cm, 20 to 500 |

Raises `ValueError` for invalid arguments, `MovementError` if the drone
rejects the command.

#### `rotate(direction, degrees)`

Turns on the spot.

| Argument | Description |
| --- | --- |
| `direction` | `'cw'` (clockwise) or `'ccw'` (counter-clockwise) |
| `degrees` | Angle in degrees, 1 to 360 |

Raises `ValueError` for invalid arguments, `RotationError` if the drone
rejects the command.

#### `go(x, y, z, speed)`

Flies in a straight line to a position relative to the current one.

| Argument | Description |
| --- | --- |
| `x` | Forward (+) or back (-) in cm, -500 to 500 |
| `y` | Left (+) or right (-) in cm, -500 to 500 |
| `z` | Up (+) or down (-) in cm, -500 to 500 |
| `speed` | Speed in cm/s, 10 to 100 |

At least one of `x`, `y` and `z` must be 20 cm or more. Raises `ValueError`
for invalid arguments, `MovementError` if the drone rejects the command.

#### `flip(direction)`

Flips the drone. `direction` is `'l'` (left), `'r'` (right), `'f'` (forward)
or `'b'` (back). Raises `ValueError` for an invalid direction,
`MovementError` if the drone rejects the command.

#### `send_rc(left_right=0, forward_back=0, up_down=0, yaw=0)`

Sets the drone's velocity. Returns immediately; the velocities stay in
effect until the next call.

| Argument | Negative | Positive |
| --- | --- | --- |
| `left_right` | Left | Right |
| `forward_back` | Back | Forward |
| `up_down` | Down | Up |
| `yaw` | Counter-clockwise | Clockwise |

Values run from -100 to 100. Values outside that range are clamped and
fractional values are rounded.

#### `hover()`

Stops the motion started with `send_rc()`. Same as `send_rc(0, 0, 0, 0)`.

#### `set_speed(speed)`

Sets the speed used by `move()`, in cm/s, 10 to 100. Raises `ValueError` if
out of range, `SpeedCommandError` if the drone rejects the command.

#### `get_speed()`

Returns the speed used by `move()` in cm/s. Raises `SpeedCommandError` if
the drone's answer cannot be understood.

### Video

#### `start_video_stream(timeout=15.0, frame_callback=None)`

Turns the camera on and waits until the stream is stable.

| Argument | Description |
| --- | --- |
| `timeout` | Maximum time to wait for the stream, in seconds |
| `frame_callback` | Optional function called with every frame on the video thread |

Raises `VideoStreamError` if the stream does not start in time or is already
running.

#### `stop_video_stream()`

Turns the camera off. Ends any running `frames()` loop.

#### `frames(timeout=5.0)`

Returns an iterator over video frames. Each frame is yielded at most once;
if the consumer is slower than the camera, intermediate frames are skipped.
The iterator ends when the stream is stopped.

Raises `VideoStreamError` if the stream has not been started, fails, or
delivers no new frame within `timeout` seconds.

#### `get_frame()`

Returns a copy of the latest frame, or `None` if there is none. Does not
wait.

Frames are `numpy.ndarray` objects of shape `(720, 960, 3)` and type
`uint8`, in BGR channel order.

### Telemetry

#### `get_status()`

Returns a [`DroneStatus`](#dronestatus) snapshot.

#### `get_battery()`

Returns the battery charge in percent.

#### `get_height()`

Returns the height above the takeoff point in cm.

#### `log_status()`

Writes a one-line summary of the telemetry to the log at `INFO` level.

### Low level

#### `send_command(command, timeout=7.0, retries=0)`

Sends any SDK command and returns the drone's answer as a string.

| Argument | Description |
| --- | --- |
| `command` | The command, for example `"wifi?"` |
| `timeout` | Seconds to wait for an answer, per attempt |
| `retries` | Extra attempts if no answer arrives. Leave at 0 for commands that move the drone |

Raises `CommandTimeoutError` if the drone does not answer and
`DroneConnectionError` if not connected. The answer is returned as is, so
check it yourself: a rejected command returns a string starting with
`error`.

### Tuning

These class attributes can be changed on an instance or a subclass.

| Attribute | Default | Description |
| --- | --- | --- |
| `TAKEOFF_TIMEOUT` | 20.0 | Seconds to wait for takeoff to complete |
| `LAND_TIMEOUT` | 20.0 | Seconds to wait for landing to complete |
| `MOVE_TIMEOUT` | 20.0 | Seconds to wait for `move`, `rotate`, `go` and `flip` to complete |
| `MIN_ALTITUDE` | 10 | Height in cm above which the drone counts as airborne |
| `STATUS_MAX_AGE` | 2.0 | Seconds after which telemetry is considered out of date |

A long movement at low speed can take longer than `MOVE_TIMEOUT`: 500 cm at
10 cm/s needs 50 seconds. Raise the timeout if you fly like that.

## DroneStatus

An immutable snapshot of the drone's telemetry.

| Attribute | Type | Description |
| --- | --- | --- |
| `battery` | `int` | Battery charge in percent |
| `altitude` | `int` | Height above the takeoff point in cm |
| `tof_distance` | `int` | Distance to the ground in cm, from the downward sensor |
| `pitch`, `roll`, `yaw` | `int` | Attitude in degrees |
| `velocity` | `Coordinate` | Speed along `x`, `y` and `z` |
| `acceleration` | `Coordinate` | Acceleration along `x`, `y` and `z` |
| `temperature` | `Temperature` | `low` and `high` temperature in °C |
| `barometer` | `float` | Raw barometer reading |
| `motor_time` | `int` | Seconds the motors have been running |
| `state` | `DroneState` | Connection and flight state |
| `timestamp` | `float` | `time.monotonic()` when the data arrived, 0.0 if none has arrived |

## DroneState

| Value | Meaning |
| --- | --- |
| `DroneState.DISCONNECTED` | Not connected |
| `DroneState.CONNECTED` | Connected, has not flown yet |
| `DroneState.FLYING` | In the air |
| `DroneState.FLYING_UNSTABLE` | In the air, but the drone reported a sensor (IMU) error at takeoff |
| `DroneState.LANDED` | Back on the ground after a flight |

## Exceptions

```
TelloError
├── DroneConnectionError
├── VideoStreamError
└── CommandError
    ├── CommandTimeoutError
    ├── TakeoffError
    ├── LandingError
    ├── MovementError
    ├── RotationError
    └── SpeedCommandError
```

| Exception | Raised when |
| --- | --- |
| `TelloError` | Base class of all errors below |
| `DroneConnectionError` | The drone cannot be reached, a local port is in use, or a command is sent while disconnected |
| `VideoStreamError` | The video stream did not start or stalled |
| `CommandError` | The drone rejected a command |
| `CommandTimeoutError` | The drone did not answer a command |
| `TakeoffError` | The drone did not take off |
| `LandingError` | The landing could not be confirmed |
| `MovementError` | The drone rejected a `move`, `go` or `flip` |
| `RotationError` | The drone rejected a `rotate` |
| `SpeedCommandError` | A speed command or query failed |
