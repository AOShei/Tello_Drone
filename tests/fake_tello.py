"""A minimal stand-in for a Tello, speaking the text SDK over UDP on localhost."""

import socket
import threading
import time


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class FakeTello:
    """Answers commands with "ok" unless told otherwise and broadcasts telemetry.

    Attributes:
        responses: Maps a command to its reply. A reply of None means the
            command is ignored, a callable is called to produce the reply.
        delays: Maps a command to the seconds to wait before replying
        received: Every command received, in order
        altitude: Height reported in the telemetry
    """

    def __init__(self, status_port: int):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(('127.0.0.1', 0))
        self._socket.settimeout(0.05)
        self.port = self._socket.getsockname()[1]
        self._status_addr = ('127.0.0.1', status_port)

        self.responses = {"battery?": "87", "speed?": "100.0"}
        self.delays = {}
        self.received = []
        self.altitude = 0
        self.send_status = True

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        last_status = 0.0
        while self._running:
            if self.send_status and time.monotonic() - last_status > 0.1:
                last_status = time.monotonic()
                state = (
                    f"pitch:1;roll:-2;yaw:3;vgx:4;vgy:5;vgz:6;templ:60;temph:62;tof:10;"
                    f"h:{self.altitude};bat:87;baro:164.98;time:7;agx:1.00;agy:-2.00;agz:-999.00;\r\n"
                )
                self._socket.sendto(state.encode(), self._status_addr)

            try:
                data, addr = self._socket.recvfrom(1024)
            except socket.timeout:
                continue
            command = data.decode()
            self.received.append(command)
            if command.startswith("rc "):
                continue

            reply = self.responses.get(command, "ok")
            if callable(reply):
                reply = reply()
            if reply is None:
                continue
            if reply == "ok":
                if command == "takeoff":
                    self.altitude = 80
                elif command in ("land", "emergency"):
                    self.altitude = 0
            if command in self.delays:
                time.sleep(self.delays[command])
            self._socket.sendto(reply.encode(), addr)

    def close(self):
        self._running = False
        self._thread.join()
        self._socket.close()
