"""Exceptions raised by tello_lib.

Everything derives from :class:`TelloError`, so ``except TelloError`` catches
any failure reported by the library.
"""


class TelloError(Exception):
    """Base class for all tello_lib errors"""


class DroneConnectionError(TelloError):
    """Raised when the connection to the drone cannot be established or is missing"""


class VideoStreamError(TelloError):
    """Raised when the video stream cannot be started or stalls"""


class CommandError(TelloError):
    """Raised when the drone rejects a command"""


class CommandTimeoutError(CommandError):
    """Raised when the drone does not answer a command in time"""


class TakeoffError(CommandError):
    """Raised when takeoff fails and the drone is not airborne"""


class LandingError(CommandError):
    """Raised when landing could not be confirmed"""


class MovementError(CommandError):
    """Raised when a movement command is rejected"""


class RotationError(CommandError):
    """Raised when a rotation command is rejected"""


class SpeedCommandError(CommandError):
    """Raised when a speed command or query fails"""
