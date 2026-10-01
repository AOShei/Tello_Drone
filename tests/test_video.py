import shutil
import subprocess
import time
import unittest

from tello_lib import VideoStreamError, VideoStreamState
from tello_lib.video import VideoStream

from .fake_tello import free_udp_port


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is needed to simulate the drone's video")
class VideoStreamTest(unittest.TestCase):
    def setUp(self):
        self.port = free_udp_port()
        self.stream = VideoStream(f"udp://127.0.0.1:{self.port}")
        self.addCleanup(self.stream.stop)

    def start_camera(self):
        """Send raw H.264 over UDP like the drone does, at the Tello's 960x720"""
        camera = subprocess.Popen(
            ["ffmpeg", "-loglevel", "quiet", "-re", "-f", "lavfi",
             "-i", "testsrc=size=960x720:rate=30", "-pix_fmt", "yuv420p",
             "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-g", "15",
             "-f", "h264", f"udp://127.0.0.1:{self.port}?pkt_size=1400"],
            stdin=subprocess.DEVNULL,
        )
        self.addCleanup(camera.wait)
        self.addCleanup(camera.kill)
        return camera

    def test_frames_are_delivered_once_each(self):
        self.start_camera()
        self.stream.start(timeout=20)
        self.assertEqual(self.stream.get_state(), VideoStreamState.STREAMING)

        frame = self.stream.get_frame()
        self.assertEqual(frame.shape, (720, 960, 3))

        # testsrc shows a running counter, so consecutive frames differ
        frames = []
        for frame in self.stream.frames():
            frames.append(frame)
            if len(frames) == 5:
                break
        for previous, current in zip(frames, frames[1:]):
            self.assertFalse((previous == current).all())

    def test_slow_consumer_skips_to_latest_frame(self):
        self.start_camera()
        self.stream.start(timeout=20)
        iterator = self.stream.frames()
        next(iterator)
        first_id = self.stream._frame_id
        time.sleep(1.0)
        next(iterator)
        # A second of video went by, the consumer got the newest frame
        # instead of working through a backlog
        self.assertGreater(self.stream._frame_id - first_id, 10)
        start = time.monotonic()
        next(iterator)
        self.assertLess(time.monotonic() - start, 0.5)

    def test_frames_iterator_ends_on_stop(self):
        self.start_camera()
        self.stream.start(timeout=20)
        iterator = self.stream.frames()
        next(iterator)
        self.stream.stop()
        self.assertEqual(list(iterator), [])
        self.assertIsNone(self.stream.get_frame())

    def test_frames_raises_when_video_stalls(self):
        camera = self.start_camera()
        self.stream.start(timeout=20)
        iterator = self.stream.frames(timeout=1.0)
        next(iterator)
        camera.kill()
        with self.assertRaises(VideoStreamError):
            for _ in iterator:
                pass

    def test_start_fails_without_video(self):
        start = time.monotonic()
        with self.assertRaises(VideoStreamError):
            self.stream.start(timeout=2)
        self.assertLess(time.monotonic() - start, 10)
        self.assertEqual(self.stream.get_state(), VideoStreamState.DISCONNECTED)

    def test_restart(self):
        self.start_camera()
        self.stream.start(timeout=20)
        self.stream.stop()
        self.stream.start(timeout=20)
        self.assertIsNotNone(self.stream.get_frame())

    def test_frames_requires_started_stream(self):
        with self.assertRaises(VideoStreamError):
            next(self.stream.frames())


if __name__ == "__main__":
    unittest.main()
