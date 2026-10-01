"""UDP command channel for the Tello text SDK."""

from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Optional, Tuple

from .exceptions import CommandError, CommandTimeoutError, DroneConnectionError

logger = logging.getLogger(__name__)


class CommandHandler:
    """Sends SDK commands to the drone and matches them with their responses.

    The Tello answers one command at a time, so commands are serialized with a
    lock. While idle, a background thread pings the drone to stop it from
    auto-landing (it does so after 15 seconds without a command).
    """

    def __init__(self, tello_addr: Tuple[str, int] = ('192.168.10.1', 8889),
                 local_port: int = 8889, keepalive_interval: float = 10.0):
        self._tello_addr = tello_addr
        self._local_port = local_port
        self._keepalive_interval = keepalive_interval
        self._keepalive_timeout = 3.0

        self._socket: Optional[socket.socket] = None
        self._command_lock = threading.Lock()
        self._last_command_time = 0.0

        self._stop_event = threading.Event()
        self._keepalive_thread: Optional[threading.Thread] = None

    def start(self):
        """Open the command socket and start the keep-alive thread

        Raises:
            DroneConnectionError: If the local port cannot be bound
        """
        if self._socket is not None:
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(('', self._local_port))
        except OSError as e:
            sock.close()
            raise DroneConnectionError(
                f"Could not bind UDP port {self._local_port}: {e}. "
                "Is another program already talking to the drone?"
            ) from e

        self._socket = sock
        self._last_command_time = time.monotonic()
        self._stop_event.clear()
        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop, name="tello-keepalive", daemon=True
        )
        self._keepalive_thread.start()

    def stop(self):
        """Stop the keep-alive thread and close the command socket"""
        self._stop_event.set()
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            self._keepalive_thread.join(timeout=self._keepalive_timeout + 2.0)
        self._keepalive_thread = None

        sock, self._socket = self._socket, None
        if sock is not None:
            sock.close()

    def send_command(self, command: str, timeout: float = 7.0, retries: int = 0) -> str:
        """
        Send a command and wait for the drone's response

        Args:
            command: Command string to send
            timeout: Time to wait for a response in seconds, per attempt
            retries: Extra attempts if no response arrives. Only use this for
                commands that are safe to repeat: if just the response was
                lost, a retried "forward 100" moves the drone twice.

        Returns:
            str: Raw response from the drone (e.g. "ok", "error", "87")

        Raises:
            DroneConnectionError: If the handler has not been started
            CommandTimeoutError: If the drone did not respond
            CommandError: If the command could not be sent
        """
        with self._command_lock:
            return self._transact(command, timeout, retries)

    def send_no_reply(self, command: str):
        """
        Send a command the drone does not answer (i.e. "rc")

        This does not wait for a command in progress, so it can be called at
        a high rate from a control loop.
        """
        sock = self._socket
        if sock is None:
            raise DroneConnectionError("Not connected to the drone")
        try:
            sock.sendto(command.encode('utf-8'), self._tello_addr)
        except OSError as e:
            raise CommandError(f"Failed to send '{command}': {e}") from e

    def _transact(self, command: str, timeout: float, retries: int) -> str:
        """Send a command and read its response. Caller must hold the command lock."""
        sock = self._socket
        if sock is None:
            raise DroneConnectionError("Not connected to the drone")

        attempts = retries + 1
        for attempt in range(1, attempts + 1):
            try:
                # A response that arrived after its command timed out would
                # otherwise be mistaken for the answer to this command
                self._discard_pending(sock)
                logger.debug("Sending command: %s", command)
                sock.sendto(command.encode('utf-8'), self._tello_addr)
                response = self._receive(sock, timeout)
            except OSError as e:
                raise CommandError(f"Failed to send '{command}': {e}") from e

            if response is not None:
                logger.debug("Received response: '%s'", response)
                self._last_command_time = time.monotonic()
                return response
            logger.warning("No response to '%s' (attempt %d/%d)", command, attempt, attempts)

        raise CommandTimeoutError(f"No response to '{command}' after {attempts} attempt(s)")

    def _receive(self, sock: socket.socket, timeout: float) -> Optional[str]:
        """Wait for a datagram from the drone, None on timeout"""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            sock.settimeout(remaining)
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                return None
            if addr[0] != self._tello_addr[0]:
                continue
            return data.decode('utf-8', errors='replace').strip()

    @staticmethod
    def _discard_pending(sock: socket.socket):
        sock.setblocking(False)
        try:
            while True:
                data, _ = sock.recvfrom(1024)
                logger.debug("Discarding stale response: %r", data)
        except BlockingIOError:
            pass

    def _keepalive_loop(self):
        """Ping the drone whenever no command has been answered for a while"""
        while not self._stop_event.wait(1.0):
            with self._command_lock:
                idle = time.monotonic() - self._last_command_time
                if idle < self._keepalive_interval or self._stop_event.is_set():
                    continue
                try:
                    logger.debug("Sending keep-alive ping")
                    self._transact("command", self._keepalive_timeout, retries=0)
                except (CommandError, DroneConnectionError) as e:
                    logger.warning("Keep-alive ping failed: %s", e)
