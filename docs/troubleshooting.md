# Troubleshooting

Turn on logging first. It usually shows what is going wrong:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Connection

### `DroneConnectionError: Failed to connect to drone`

The drone did not answer.

- Check that your computer is connected to the drone's Wi-Fi network
  (`TELLO-XXXXXX`). Some systems switch back to another network because the
  drone's has no internet access.
- Check that the drone is on and its light is blinking.
- Close the Tello app on any device connected to the drone.
- Check that a VPN is not routing the traffic elsewhere.

### `DroneConnectionError: Could not bind UDP port ...`

Another program on your computer is using the port, most often a previous
run of your own script that is still alive. Stop it and try again.

### `No telemetry received on UDP port 8890, check your firewall`

Commands work, but the drone's status broadcasts do not reach your program.
Allow incoming UDP on port 8890 in your firewall. Without telemetry,
`get_status()` returns zeros.

## Video

### `VideoStreamError: Video stream failed to stabilize`

- Allow incoming UDP on port 11111 in your firewall. This is the most common cause.
- Check that no other program is receiving the drone's video.
- Give it more time: `drone.start_video_stream(timeout=30)`.

### Decoder warnings in the terminal

Messages such as `non-existing PPS 0 referenced` or `error while decoding`
come from the video decoder. A few of them at startup are normal: the
decoder joins the stream mid-way and has to wait for a complete frame. Many
of them during flight mean the Wi-Fi link is weak. Move closer to the drone.

### The video window does not appear or freezes

Call `cv2.imshow()` and `cv2.waitKey()` from the main thread, and make sure
`cv2.waitKey()` is called regularly. The window is only updated inside that
call.

If `cv2.imshow` raises an error saying it is not implemented, you have a
headless OpenCV build installed. Replace it:

```bash
pip uninstall opencv-python-headless
pip install opencv-python
```

### The video lags behind

Use `drone.frames()` or `drone.get_frame()`, which always return the latest
image. If you collect frames in your own queue with a callback, the queue is
where the delay builds up.

## Flight

### `TakeoffError`

- The battery is too low. Check `drone.get_battery()`.
- The drone is not on a level surface.
- The drone is too hot. It overheats when it sits on the ground switched on
  for a long time, especially with the video on, because it relies on the
  propellers for cooling. Let it cool down.

### A command raises an error containing `error Not joystick`

This usually means the drone was still busy with something else. Wait a
moment after takeoff before sending the first movement.

### A command raises an error containing `error No valid imu`

The drone cannot determine its position. This usually happens in poor light
or over floors without visible texture. Fly somewhere brighter.

### `CommandTimeoutError` on a long movement

The movement took longer than the library waits for it. Raise the timeout:

```python
drone.MOVE_TIMEOUT = 60
```

### The drone lands by itself

- The battery is low.
- The drone overheated.
- Your program stopped talking to it, for example because it crashed or the
  Wi-Fi connection dropped. The drone lands after 15 seconds without commands.

### The drone drifts

It holds its position using a camera that looks at the floor. Fly over a
well-lit surface with visible detail, and avoid reflective or uniform floors.
