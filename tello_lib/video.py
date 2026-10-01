"""Video stream receiver for the Tello's H.264 feed."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Iterator, Optional

import cv2
import numpy as np

from .exceptions import VideoStreamError
from .models import VideoStreamState

logger = logging.getLogger(__name__)


class VideoStream:
    """Decodes the drone's video on a background thread, keeping only the latest frame.

    Frames are BGR ``numpy`` arrays (960x720 on a standard Tello), ready to
    pass to OpenCV or a detector such as YOLO.
    """

    def __init__(self, url: str = "udp://0.0.0.0:11111"):
        self._url = url
        self._stop_event = threading.Event()
        self._frame_callback: Optional[Callable[[np.ndarray], None]] = None
        self._thread: Optional[threading.Thread] = None

        # Guards the latest frame and its sequence number, and wakes up
        # consumers waiting for a new frame
        self._frame_condition = threading.Condition()
        self._last_frame: Optional[np.ndarray] = None
        self._frame_id = 0

        self._state = VideoStreamState.DISCONNECTED
        self._state_lock = threading.Lock()
        self._frame_validation_threshold = 30  # Valid frames needed before the stream counts as stable
        self._frame_timeout = 5.0

    def start(self, frame_callback: Optional[Callable[[np.ndarray], None]] = None,
              timeout: float = 15.0):
        """
        Start video stream and wait for stable connection

        Args:
            frame_callback: Optional callback invoked with every decoded frame.
                It runs on the video thread, so keep it fast.
            timeout: Maximum time to wait for stable stream in seconds

        Raises:
            VideoStreamError: If the stream is already running or did not
                stabilize within the timeout
        """
        with self._state_lock:
            if self._state != VideoStreamState.DISCONNECTED:
                raise VideoStreamError("Video stream is already started")
            self._state = VideoStreamState.INITIALIZING

        self._frame_callback = frame_callback
        # Each run gets its own stop event, so a thread still blocked in a
        # read from a previous run cannot be revived by a restart
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._video_loop, args=(self._stop_event, timeout),
            name="tello-video", daemon=True
        )
        self._thread.start()

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.get_state()
            if state == VideoStreamState.STREAMING:
                return
            if state == VideoStreamState.ERROR:
                break
            time.sleep(0.05)

        self.stop()
        raise VideoStreamError(f"Video stream failed to stabilize within {timeout:.0f} seconds")

    def _video_loop(self, stop_event: threading.Event, open_timeout: float):
        """Video capture loop"""
        cap = None
        try:
            # Opening blocks until the first keyframe arrives, so it is done
            # here rather than in start()
            cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG, [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(open_timeout * 1000),
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(self._frame_timeout * 1000),
            ])
            if not cap.isOpened():
                raise VideoStreamError("Failed to open video capture")

            valid_frames = 0
            last_frame_time = time.monotonic()

            while not stop_event.is_set():
                ret, frame = cap.read()

                if ret and frame is not None and frame.size > 0:
                    last_frame_time = time.monotonic()
                    valid_frames += 1

                    if stop_event.is_set():
                        break
                    if valid_frames >= self._frame_validation_threshold:
                        with self._frame_condition:
                            self._last_frame = frame
                            self._frame_id += 1
                            self._frame_condition.notify_all()
                        with self._state_lock:
                            if self._state == VideoStreamState.INITIALIZING:
                                self._state = VideoStreamState.STREAMING
                                logger.info("Video stream stabilized")

                        if self._frame_callback:
                            try:
                                self._frame_callback(frame)
                            except Exception:
                                logger.exception("Error in frame callback")

                elif time.monotonic() - last_frame_time > self._frame_timeout:
                    raise VideoStreamError("No video frames received")
                else:
                    time.sleep(0.01)

        except Exception as e:
            if not stop_event.is_set():
                logger.error("Video stream error: %s", e)
                with self._state_lock:
                    self._state = VideoStreamState.ERROR
        finally:
            if cap is not None:
                cap.release()
            # Wake up anyone blocked in frames()
            with self._frame_condition:
                self._frame_condition.notify_all()

    def get_frame(self) -> Optional[np.ndarray]:
        """Get a copy of the latest video frame, None if there is none yet"""
        with self._frame_condition:
            return self._last_frame.copy() if self._last_frame is not None else None

    def frames(self, timeout: float = 5.0) -> Iterator[np.ndarray]:
        """
        Iterate over frames as they arrive

        Each frame is yielded at most once. If the consumer is slower than the
        stream (e.g. it runs a detector on every frame) the frames in between
        are skipped, so the loop always works on the most recent image.

        The iterator ends when the stream is stopped.

        Args:
            timeout: Maximum time to wait for a new frame in seconds

        Raises:
            VideoStreamError: If the stream fails or no new frame arrives in time
        """
        if self.get_state() == VideoStreamState.DISCONNECTED:
            raise VideoStreamError("Video stream is not started")

        last_id = 0
        while True:
            with self._frame_condition:
                arrived = self._frame_condition.wait_for(
                    lambda: self._frame_id != last_id or self.get_state() != VideoStreamState.STREAMING,
                    timeout=timeout,
                )
                state = self.get_state()
                if state == VideoStreamState.DISCONNECTED:
                    return
                if state == VideoStreamState.ERROR:
                    raise VideoStreamError("Video stream failed")
                if not arrived or self._last_frame is None:
                    raise VideoStreamError(f"No video frame received for {timeout:.0f} seconds")
                last_id = self._frame_id
                frame = self._last_frame.copy()
            yield frame

    def get_state(self) -> VideoStreamState:
        """Get current stream state"""
        with self._state_lock:
            return self._state

    def stop(self):
        """Stop video stream"""
        self._stop_event.set()
        thread, self._thread = self._thread, None
        if thread and thread.is_alive() and thread is not threading.current_thread():
            # The thread may be blocked in a read; it exits once that times out
            thread.join(timeout=self._frame_timeout + 1.0)
        with self._state_lock:
            self._state = VideoStreamState.DISCONNECTED
        with self._frame_condition:
            self._last_frame = None
            self._frame_id = 0
            self._frame_condition.notify_all()
