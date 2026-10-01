"""High-level controller for a Tello drone."""

from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import replace
from typing import Callable, Iterator, Optional, Type

import numpy as np

from .command_handler import CommandHandler
from .exceptions import (
    CommandError,
    CommandTimeoutError,
    DroneConnectionError,
    LandingError,
    MovementError,
    RotationError,
    SpeedCommandError,
    TakeoffError,
    TelloError,
)
from .models import DroneState, DroneStatus, VideoStreamState
from .video import VideoStream

logger = logging.getLogger(__name__)


class TelloController:
    """Controls a Tello over its Wi-Fi text SDK.

    Use it as a context manager to make sure the drone lands and all
    resources are released, even if your code raises::

        with TelloController() as drone:
            drone.takeoff()
            drone.move("forward", 50)
            drone.land()

    Commands raise a :class:`~tello_lib.exceptions.TelloError` subclass when
    they fail.
    """

    MIN_ALTITUDE = 10  # cm, above this the drone is considered airborne
    TAKEOFF_TIMEOUT = 20.0
    LAND_TIMEOUT = 20.0
    MOVE_TIMEOUT = 20.0
    STATUS_MAX_AGE = 2.0  # seconds, older telemetry is not trusted

    def __init__(self, host: str = '192.168.10.1', *, command_port: int = 8889,
                 local_command_port: int = 8889, status_port: int = 8890,
                 video_port: int = 11111):
        """
        Args:
            host: IP address of the drone
            command_port: UDP port the drone listens on for commands
            local_command_port: Local UDP port commands are sent from
            status_port: Local UDP port the drone sends its telemetry to
            video_port: Local UDP port the drone sends its video to
        """
        self._command_handler = CommandHandler((host, command_port), local_command_port)
        self._video = VideoStream(f"udp://0.0.0.0:{video_port}")
        self._status_port = status_port

        self._state = DroneState.DISCONNECTED
        self._status = DroneStatus()
        self._status_received = threading.Event()

        # Status monitoring
        self._status_socket: Optional[socket.socket] = None
        self._status_thread: Optional[threading.Thread] = None
        self._running = False

    def __enter__(self) -> "TelloController":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.is_flying:
            try:
                self.land()
            except TelloError as e:
                logger.error("Failed to land on exit: %s", e)
        self.disconnect()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self):
        """
        Initialize connection to the drone

        Raises:
            DroneConnectionError: If the drone does not respond or the local
                ports are unavailable
        """
        if self._state != DroneState.DISCONNECTED:
            return

        try:
            self._command_handler.start()
            self._start_status_monitor()

            logger.info("Entering SDK mode...")
            response = self._command_handler.send_command("command", timeout=3.0, retries=2)
            if response.lower() != "ok":
                raise DroneConnectionError(f"Unexpected response during connection: {response}")
        except TelloError as e:
            self._release()
            if isinstance(e, DroneConnectionError):
                raise
            raise DroneConnectionError(
                f"Failed to connect to drone: {e}. Is this computer on the drone's Wi-Fi network?"
            ) from e

        self._state = DroneState.CONNECTED
        logger.info("Connected to drone")

        # Telemetry arrives ~10 times a second, give the first packet a moment
        # so get_battery() and friends are usable right away
        if not self._status_received.wait(timeout=2.0):
            logger.warning(
                "No telemetry received on UDP port %d, check your firewall", self._status_port
            )

    def disconnect(self):
        """Disconnect from the drone and release all resources

        This does not land the drone. Without commands it lands on its own
        after 15 seconds.
        """
        if self._state == DroneState.DISCONNECTED:
            return
        if self.is_flying:
            logger.warning("Disconnecting while the drone is still flying")

        if self._video.get_state() != VideoStreamState.DISCONNECTED:
            try:
                self.stop_video_stream()
            except TelloError as e:
                logger.warning("Failed to stop video stream: %s", e)

        self._release()
        logger.info("Disconnected from drone")

    def _release(self):
        self._running = False
        thread, self._status_thread = self._status_thread, None
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        sock, self._status_socket = self._status_socket, None
        if sock is not None:
            sock.close()

        self._video.stop()
        self._command_handler.stop()
        self._status_received.clear()
        self._status = DroneStatus()
        self._state = DroneState.DISCONNECTED

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    def _start_status_monitor(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(('', self._status_port))
        except OSError as e:
            sock.close()
            raise DroneConnectionError(
                f"Could not bind UDP port {self._status_port}: {e}. "
                "Is another program already talking to the drone?"
            ) from e
        sock.settimeout(1.0)

        self._status_socket = sock
        self._running = True
        self._status_thread = threading.Thread(
            target=self._status_loop, args=(sock,), name="tello-status", daemon=True
        )
        self._status_thread.start()

    def _status_loop(self, sock: socket.socket):
        """Status monitoring loop"""
        while self._running:
            try:
                data, _ = sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break  # Socket closed

            try:
                raw_status = data.decode('utf-8', errors='replace')
                self._status = DroneStatus.from_state_string(raw_status, time.monotonic())
                self._status_received.set()
            except ValueError as e:
                logger.debug("Ignoring malformed status packet: %s", e)

    def _fresh_altitude(self) -> Optional[int]:
        """Altitude in cm from recent telemetry, None if telemetry is missing or stale"""
        status = self._status
        if not status.timestamp or time.monotonic() - status.timestamp > self.STATUS_MAX_AGE:
            return None
        return status.altitude

    @property
    def state(self) -> DroneState:
        """Current connection/flight state"""
        return self._state

    @property
    def is_flying(self) -> bool:
        return self._state in (DroneState.FLYING, DroneState.FLYING_UNSTABLE)

    def get_status(self) -> DroneStatus:
        """Get a snapshot of the current drone status"""
        return replace(self._status, state=self._state)

    def get_battery(self) -> int:
        """Get battery percentage"""
        if self._status_received.is_set():
            return self._status.battery
        response = self.send_command("battery?", retries=2)
        try:
            return int(float(response))
        except ValueError:
            raise CommandError(f"Unexpected response to battery query: {response}") from None

    def get_height(self) -> int:
        """Get current height above the takeoff point in centimeters"""
        return self._status.altitude

    def log_status(self):
        """Log all drone status values for debugging"""
        s = self._status
        logger.info(
            "Drone[BAT:%d%% POS(p:%d° r:%d° y:%d°) ALT:%dcm TOF:%dcm "
            "TEMP(%d°C,%d°C) TIME:%ds STATE:%s]",
            s.battery, s.pitch, s.roll, s.yaw, s.altitude, s.tof_distance,
            s.temperature.low, s.temperature.high, s.motor_time, self._state.name,
        )

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def send_command(self, command: str, timeout: float = 7.0, retries: int = 0) -> str:
        """
        Send a raw SDK command and return the drone's response

        Use this for SDK commands that have no dedicated method.

        Raises:
            CommandTimeoutError: If the drone did not respond
        """
        return self._command_handler.send_command(command, timeout=timeout, retries=retries)

    def _send_expect_ok(self, command: str, error: Type[CommandError] = CommandError,
                        timeout: float = 7.0, retries: int = 0):
        response = self.send_command(command, timeout=timeout, retries=retries)
        if response.lower() != "ok":
            raise error(f"Drone rejected '{command}': {response}")

    def takeoff(self):
        """
        Take off the drone

        Raises:
            TakeoffError: If the drone did not take off
        """
        if self._state not in (DroneState.CONNECTED, DroneState.LANDED):
            raise TakeoffError(f"Cannot take off while {self._state.value}")

        try:
            response = self.send_command("takeoff", timeout=self.TAKEOFF_TIMEOUT)
        except CommandTimeoutError:
            response = None

        if response is not None and response.lower() == "ok":
            self._state = DroneState.FLYING
            logger.info("Takeoff complete")
            return

        # The drone can be airborne even though the command reported a
        # problem, the telemetry tells
        time.sleep(2)
        altitude = self._fresh_altitude()
        if altitude is not None and altitude > self.MIN_ALTITUDE:
            if response is not None and "imu" in response.lower():
                self._state = DroneState.FLYING_UNSTABLE
            else:
                self._state = DroneState.FLYING
            logger.warning("Drone is airborne despite takeoff response: %s", response)
            return

        raise TakeoffError(f"Takeoff failed: {response or 'no response'}")

    def land(self):
        """
        Land the drone

        Raises:
            LandingError: If the landing could not be confirmed
        """
        try:
            response = self.send_command("land", timeout=self.LAND_TIMEOUT)
        except CommandTimeoutError:
            response = None

        if response is not None and response.lower() == "ok":
            self._state = DroneState.LANDED
            logger.info("Landing complete")
            return

        # Check if drone actually landed despite the error
        time.sleep(3)
        altitude = self._fresh_altitude()
        if altitude is not None and altitude <= self.MIN_ALTITUDE:
            self._state = DroneState.LANDED
            logger.warning("Drone is on the ground despite land response: %s", response)
            return

        raise LandingError(f"Landing not confirmed: {response or 'no response'}")

    def emergency(self):
        """Stop all motors immediately. The drone will drop, use land() if you can."""
        try:
            self.send_command("emergency", timeout=2.0, retries=2)
        finally:
            self._state = DroneState.LANDED

    def move(self, direction: str, distance: int):
        """
        Move the drone in a direction

        Args:
            direction: One of 'up', 'down', 'left', 'right', 'forward', 'back'
            distance: Distance in centimeters, 20 to 500

        Raises:
            MovementError: If the drone rejected the command
        """
        if direction not in ('up', 'down', 'left', 'right', 'forward', 'back'):
            raise ValueError("Invalid direction")
        if not 20 <= distance <= 500:
            raise ValueError("Distance must be between 20 and 500 cm")

        self._send_expect_ok(f"{direction} {int(distance)}", MovementError, self.MOVE_TIMEOUT)

    def go(self, x: int, y: int, z: int, speed: int):
        """
        Fly to a position relative to the current one

        Args:
            x: Distance forward (+) or back (-) in centimeters, -500 to 500
            y: Distance left (+) or right (-) in centimeters, -500 to 500
            z: Distance up (+) or down (-) in centimeters, -500 to 500
            speed: Speed in cm/s, 10 to 100

        Raises:
            MovementError: If the drone rejected the command
        """
        if not all(-500 <= v <= 500 for v in (x, y, z)):
            raise ValueError("x, y and z must be between -500 and 500 cm")
        if all(-20 < v < 20 for v in (x, y, z)):
            raise ValueError("At least one of x, y and z must be 20 cm or more")
        if not 10 <= speed <= 100:
            raise ValueError("Speed must be between 10 and 100 cm/s")

        self._send_expect_ok(
            f"go {int(x)} {int(y)} {int(z)} {int(speed)}", MovementError, self.MOVE_TIMEOUT
        )

    def rotate(self, direction: str, degrees: int):
        """
        Rotate the drone

        Args:
            direction: 'cw' (clockwise) or 'ccw' (counter-clockwise)
            degrees: Angle in degrees, 1 to 360

        Raises:
            RotationError: If the drone rejected the command
        """
        if direction not in ('cw', 'ccw'):
            raise ValueError("Invalid rotation direction")
        if not 1 <= degrees <= 360:
            raise ValueError("Degrees must be between 1 and 360")

        self._send_expect_ok(f"{direction} {int(degrees)}", RotationError, self.MOVE_TIMEOUT)

    def flip(self, direction: str):
        """
        Flip the drone

        Args:
            direction: 'l' (left), 'r' (right), 'f' (forward) or 'b' (back)

        Raises:
            MovementError: If the drone rejected the command
        """
        if direction not in ('l', 'r', 'f', 'b'):
            raise ValueError("Invalid flip direction")

        self._send_expect_ok(f"flip {direction}", MovementError, self.MOVE_TIMEOUT)

    def send_rc(self, left_right: int = 0, forward_back: int = 0,
                up_down: int = 0, yaw: int = 0):
        """
        Set the drone's velocity, like holding the sticks of a remote control

        This is the command to use for closed-loop control (e.g. following a
        detected object): it returns immediately and the drone keeps flying
        at the given velocities until the next call. Values are -100 to 100
        and are clamped to that range.

        Args:
            left_right: Left (-) / right (+)
            forward_back: Back (-) / forward (+)
            up_down: Down (-) / up (+)
            yaw: Counter-clockwise (-) / clockwise (+)
        """
        values = [max(-100, min(100, int(round(v)))) for v in (left_right, forward_back, up_down, yaw)]
        self._command_handler.send_no_reply("rc {} {} {} {}".format(*values))

    def hover(self):
        """Stop any motion started with send_rc() and hover in place"""
        self.send_rc(0, 0, 0, 0)

    def set_speed(self, speed: int):
        """
        Set the speed used by move() in cm/s, 10 to 100

        Raises:
            SpeedCommandError: If the drone rejected the command
        """
        if not 10 <= speed <= 100:
            raise ValueError("Speed must be between 10 and 100 cm/s")

        self._send_expect_ok(f"speed {int(speed)}", SpeedCommandError, retries=2)

    def get_speed(self) -> int:
        """
        Get the speed used by move() in centimeters per second

        Raises:
            SpeedCommandError: If the response could not be understood
        """
        response = self.send_command("speed?", retries=2)
        try:
            return int(float(response))
        except ValueError:
            raise SpeedCommandError(f"Could not parse speed from response: {response}") from None

    # ------------------------------------------------------------------
    # Video
    # ------------------------------------------------------------------

    def start_video_stream(self, timeout: float = 15.0,
                           frame_callback: Optional[Callable[[np.ndarray], None]] = None):
        """
        Start the video stream and wait for it to stabilize

        Args:
            timeout: Maximum time to wait for stable stream in seconds
            frame_callback: Optional callback invoked with every frame on the
                video thread. Most code should use frames() or get_frame().

        Raises:
            VideoStreamError: If the stream did not start
        """
        self._send_expect_ok("streamon", retries=2)
        self._video.start(frame_callback=frame_callback, timeout=timeout)

    def stop_video_stream(self):
        """Stop the video stream"""
        self._video.stop()
        self._send_expect_ok("streamoff", retries=2)

    def get_frame(self) -> Optional[np.ndarray]:
        """Get the latest video frame as a BGR image, None if there is none yet"""
        return self._video.get_frame()

    def frames(self, timeout: float = 5.0) -> Iterator[np.ndarray]:
        """
        Iterate over video frames as they arrive

        Each frame is yielded at most once and frames are skipped if the loop
        body is slower than the stream, so this is the natural way to feed a
        detector::

            for frame in drone.frames():
                results = model(frame)

        The iterator ends when the video stream is stopped.

        Raises:
            VideoStreamError: If no new frame arrives within the timeout
        """
        return self._video.frames(timeout=timeout)
