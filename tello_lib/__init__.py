"""Python library for controlling Tello drones."""

from .controller import TelloController
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
    VideoStreamError,
)
from .models import Coordinate, DroneState, DroneStatus, Temperature, VideoStreamState

__version__ = "0.1.0"

__all__ = [
    "TelloController",
    "DroneState",
    "DroneStatus",
    "VideoStreamState",
    "Coordinate",
    "Temperature",
    "TelloError",
    "DroneConnectionError",
    "VideoStreamError",
    "CommandError",
    "CommandTimeoutError",
    "TakeoffError",
    "LandingError",
    "MovementError",
    "RotationError",
    "SpeedCommandError",
]
