# Flight control

There are two ways to fly the drone. They can be mixed in one program.

| | Step-by-step commands | Velocity control |
| --- | --- | --- |
| Methods | `move`, `rotate`, `go`, `flip` | `send_rc`, `hover` |
| Returns | When the drone has finished | Immediately |
| Good for | Scripted flights | Control loops driven by the camera |

## Takeoff and landing

```python
drone.takeoff()
drone.land()
```

Both wait until the drone has finished. `takeoff()` raises `TakeoffError` if
the drone stays on the ground, `land()` raises `LandingError` if the landing
could not be confirmed.

`drone.emergency()` cuts the motors immediately. The drone drops, so use it
only when a normal landing is not an option.

## Step-by-step commands

```python
drone.move("forward", 100)      # up, down, left, right, forward, back; 20-500 cm
drone.rotate("cw", 90)          # cw or ccw; 1-360 degrees
drone.go(100, 0, 50, speed=40)  # 100 cm forward and 50 cm up, at 40 cm/s
drone.flip("f")                 # l, r, f, b
drone.set_speed(50)             # speed used by move(), 10-100 cm/s
```

Each call blocks until the drone reports that the movement is complete, so
the calls above run one after the other.

Arguments outside the allowed range raise `ValueError` before anything is
sent. If the drone refuses a command, for example a flip on a low battery,
the method raises an error that includes the drone's answer.

## Velocity control

```python
drone.send_rc(left_right=0, forward_back=20, up_down=0, yaw=30)
```

`send_rc()` works like holding the sticks of a remote control. Each value
runs from -100 to 100:

| Argument | Negative | Positive |
| --- | --- | --- |
| `left_right` | Left | Right |
| `forward_back` | Back | Forward |
| `up_down` | Down | Up |
| `yaw` | Turn counter-clockwise | Turn clockwise |

The call returns immediately and the drone keeps flying at these velocities
until you send new ones. To stop, send zeros:

```python
drone.hover()   # same as drone.send_rc(0, 0, 0, 0)
```

Values outside -100 to 100 are clamped, and fractional values are rounded,
so you can pass the output of a controller directly.

A typical control loop calls `send_rc()` once per video frame. See
[Video and vision](video.md#from-detection-to-motion) for how to derive the
values from an image.

Things to keep in mind:

- The drone does not acknowledge `rc` commands, so `send_rc()` cannot tell
  you whether the command arrived. The next call replaces it anyway.
- Always end a control loop with `hover()` or `land()`. Leaving a `with`
  block lands the drone for you.

## Telemetry

The drone broadcasts its state about ten times a second. `get_status()`
returns the latest snapshot:

```python
status = drone.get_status()

status.battery          # percent
status.altitude         # cm above the takeoff point
status.tof_distance     # cm to the ground, from the downward sensor
status.pitch            # degrees; also roll and yaw
status.velocity.x       # also .y and .z
status.acceleration.x   # also .y and .z
status.temperature.high # °C; also .low
status.motor_time       # seconds the motors have been running
status.state            # DroneState
```

A status object is a snapshot and does not change after you get it. Call
`get_status()` again for fresh values.

Shortcuts for common values:

```python
drone.get_battery()   # percent
drone.get_height()    # cm
drone.is_flying       # True or False
drone.state           # DroneState.CONNECTED, FLYING, LANDED, ...
```

## Error handling

All errors raised by the library derive from `TelloError`.

```python
from tello_lib import TelloController, TelloError, MovementError

try:
    with TelloController() as drone:
        drone.takeoff()
        try:
            drone.move("forward", 300)
        except MovementError as e:
            print(f"Could not move: {e}")   # carry on with the flight
        drone.land()
except TelloError as e:
    print(f"Flight aborted: {e}")
```

| Exception | Raised when |
| --- | --- |
| `DroneConnectionError` | The drone cannot be reached or a local port is in use |
| `CommandError` | The drone rejected a command |
| `CommandTimeoutError` | The drone did not answer a command |
| `TakeoffError`, `LandingError` | Takeoff or landing could not be confirmed |
| `MovementError`, `RotationError`, `SpeedCommandError` | The drone rejected that kind of command |
| `VideoStreamError` | The video stream did not start or stalled |

`CommandTimeoutError`, `TakeoffError`, `LandingError`, `MovementError`,
`RotationError`, and `SpeedCommandError` are subclasses of `CommandError`.

A movement command that gets no answer is **not** sent again. The command
may have arrived and only the answer got lost, and repeating it would move
the drone twice. When you get a `CommandTimeoutError` from a movement,
check the telemetry or the camera before deciding what to do next.

## Staying connected

A Tello lands by itself when it receives no command for 15 seconds. The
library sends a keep-alive in the background whenever your program is busy
with something else, so you do not have to think about this.

## Other SDK commands

Commands without a dedicated method can be sent with `send_command()`, which
returns the drone's answer as a string:

```python
wifi = drone.send_command("wifi?")    # Wi-Fi signal strength
time = drone.send_command("time?")    # flight time
```

## Using threads

Commands that wait for an answer are sent one at a time. If two threads call
such methods at the same moment, the second waits for the first to finish.
`send_rc()` never waits, and video and telemetry can be read from any thread
at any time.

## Safety checklist

- Use the `with` block, so the drone lands when your program stops for any reason.
- Check the battery before takeoff. The drone refuses to take off, and
  refuses flips even earlier, when the battery is low.
- Try new vision code on the ground first, with the commands printed instead of sent.
- Keep velocities low while tuning a control loop.
- Fly in a space with good, even lighting. The drone holds its position with
  a downward camera and drifts over dark or featureless floors.
