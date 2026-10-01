"""Data types shared across tello_lib."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DroneState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    FLYING = "flying"
    FLYING_UNSTABLE = "flying_unstable"  # Airborne, but the drone reported an IMU error
    LANDED = "landed"


class VideoStreamState(Enum):
    DISCONNECTED = "disconnected"
    INITIALIZING = "initializing"
    STREAMING = "streaming"
    ERROR = "error"


@dataclass(frozen=True)
class Coordinate:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass(frozen=True)
class Temperature:
    low: int = 0
    high: int = 0


@dataclass(frozen=True)
class DroneStatus:
    """Snapshot of the telemetry the drone broadcasts on its state port.

    Attributes:
        pitch, roll, yaw: Attitude in degrees
        velocity: Speed along each axis (``vgx``/``vgy``/``vgz``)
        acceleration: Acceleration along each axis (``agx``/``agy``/``agz``)
        temperature: Lowest and highest board temperature in °C
        tof_distance: Time-of-flight sensor distance to the ground in cm
        altitude: Height relative to the takeoff point in cm
        battery: Battery charge in percent
        barometer: Raw barometer reading
        motor_time: Time the motors have been running in seconds
        state: Connection/flight state tracked by the controller
        timestamp: ``time.monotonic()`` when the packet arrived, 0.0 if no
            telemetry has been received yet
    """

    pitch: int = 0
    roll: int = 0
    yaw: int = 0
    velocity: Coordinate = field(default_factory=Coordinate)
    acceleration: Coordinate = field(default_factory=Coordinate)
    temperature: Temperature = field(default_factory=Temperature)
    tof_distance: int = 0
    altitude: int = 0
    battery: int = 0
    barometer: float = 0.0
    motor_time: int = 0
    state: DroneState = DroneState.DISCONNECTED
    timestamp: float = 0.0

    @classmethod
    def from_state_string(cls, raw: str, timestamp: float = 0.0) -> "DroneStatus":
        """Parse a state packet such as ``pitch:0;roll:0;yaw:0;...;bat:87;...``.

        Fields are matched by name, so extra fields (e.g. the mission pad
        data sent by the Tello EDU) are ignored and missing ones default to 0.

        Raises:
            ValueError: If the packet contains no ``key:value`` pairs
        """
        values = {}
        for item in raw.strip().split(';'):
            key, sep, value = item.partition(':')
            if sep:
                values[key.strip()] = value.strip()
        if not values:
            raise ValueError(f"Not a state packet: {raw!r}")

        def number(key: str, cast=int):
            try:
                return cast(float(values[key]))
            except (KeyError, ValueError):
                return cast(0)

        return cls(
            pitch=number('pitch'),
            roll=number('roll'),
            yaw=number('yaw'),
            velocity=Coordinate(number('vgx', float), number('vgy', float), number('vgz', float)),
            acceleration=Coordinate(number('agx', float), number('agy', float), number('agz', float)),
            temperature=Temperature(number('templ'), number('temph')),
            tof_distance=number('tof'),
            altitude=number('h'),
            battery=number('bat'),
            barometer=number('baro', float),
            motor_time=number('time'),
            timestamp=timestamp,
        )
