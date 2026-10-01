import socket
import time
import unittest

from tello_lib import (
    CommandTimeoutError,
    DroneConnectionError,
    DroneState,
    LandingError,
    MovementError,
    TakeoffError,
    TelloController,
)

from .fake_tello import FakeTello, free_udp_port


class ControllerTestCase(unittest.TestCase):
    def setUp(self):
        self.status_port = free_udp_port()
        self.tello = FakeTello(self.status_port)
        self.addCleanup(self.tello.close)
        self.drone = self.make_controller()
        self.addCleanup(self.drone.disconnect)

    def make_controller(self) -> TelloController:
        return TelloController(
            '127.0.0.1', command_port=self.tello.port, local_command_port=0,
            status_port=self.status_port,
        )


class ConnectionTest(ControllerTestCase):
    def test_connect_enters_sdk_mode_and_receives_telemetry(self):
        self.drone.connect()
        self.assertEqual(self.tello.received[0], "command")
        self.assertEqual(self.drone.state, DroneState.CONNECTED)
        self.assertEqual(self.drone.get_battery(), 87)
        self.assertEqual(self.drone.get_status().state, DroneState.CONNECTED)

    def test_connect_fails_when_drone_is_silent(self):
        self.tello.responses["command"] = None
        with self.assertRaises(DroneConnectionError):
            self.drone.connect()
        self.assertEqual(self.drone.state, DroneState.DISCONNECTED)

        # Ports were released, so a later attempt works
        self.tello.responses.pop("command")
        self.drone.connect()
        self.assertEqual(self.drone.state, DroneState.CONNECTED)

    def test_connect_reports_port_in_use(self):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        blocker.bind(('', free_udp_port()))
        self.addCleanup(blocker.close)
        drone = TelloController(
            '127.0.0.1', command_port=self.tello.port, local_command_port=0,
            status_port=blocker.getsockname()[1],
        )
        with self.assertRaises(DroneConnectionError):
            drone.connect()

    def test_reconnect_after_disconnect(self):
        self.drone.connect()
        self.drone.disconnect()
        self.assertEqual(self.drone.state, DroneState.DISCONNECTED)
        self.drone.connect()
        self.assertEqual(self.drone.get_battery(), 87)

    def test_battery_falls_back_to_query_without_telemetry(self):
        self.tello.send_status = False
        self.drone.connect()
        self.assertEqual(self.drone.get_battery(), 87)
        self.assertIn("battery?", self.tello.received)

    def test_context_manager_lands_and_disconnects_on_error(self):
        drone = self.make_controller()
        with self.assertRaises(RuntimeError):
            with drone:
                drone.takeoff()
                raise RuntimeError("user code failed")
        self.assertIn("land", self.tello.received)
        self.assertEqual(drone.state, DroneState.DISCONNECTED)


class FlightTest(ControllerTestCase):
    def setUp(self):
        super().setUp()
        self.drone.connect()

    def test_takeoff_move_land(self):
        self.drone.takeoff()
        self.assertTrue(self.drone.is_flying)
        self.drone.move("forward", 50)
        self.drone.rotate("cw", 90)
        self.drone.go(50, -30, 0, 40)
        self.drone.flip("l")
        self.drone.land()
        self.assertEqual(self.drone.state, DroneState.LANDED)
        self.assertEqual(
            self.tello.received[1:],
            ["takeoff", "forward 50", "cw 90", "go 50 -30 0 40", "flip l", "land"],
        )

    def test_can_take_off_again_after_landing(self):
        self.drone.takeoff()
        self.drone.land()
        self.drone.takeoff()
        self.assertEqual(self.drone.state, DroneState.FLYING)

    def test_takeoff_rejected(self):
        self.tello.responses["takeoff"] = "error"
        with self.assertRaises(TakeoffError):
            self.drone.takeoff()
        self.assertEqual(self.drone.state, DroneState.CONNECTED)

    def test_takeoff_error_but_airborne(self):
        def imu_error():
            self.tello.altitude = 80
            return "error No valid imu"
        self.tello.responses["takeoff"] = imu_error
        self.drone.takeoff()
        self.assertEqual(self.drone.state, DroneState.FLYING_UNSTABLE)

    def test_takeoff_response_lost_but_airborne(self):
        def lost():
            self.tello.altitude = 80
        self.tello.responses["takeoff"] = lost
        self.drone.TAKEOFF_TIMEOUT = 0.3
        self.drone.takeoff()
        self.assertEqual(self.drone.state, DroneState.FLYING)

    def test_takeoff_not_assumed_without_telemetry(self):
        self.tello.send_status = False
        self.tello.responses["takeoff"] = None
        self.drone.TAKEOFF_TIMEOUT = 0.3
        self.drone.STATUS_MAX_AGE = 0.5
        with self.assertRaises(TakeoffError):
            self.drone.takeoff()

    def test_landing_not_confirmed_keeps_flying_state(self):
        self.drone.takeoff()
        self.tello.responses["land"] = "error"
        with self.assertRaises(LandingError):
            self.drone.land()
        self.assertTrue(self.drone.is_flying)

    def test_move_rejected(self):
        self.tello.responses["forward 50"] = "error Not joystick"
        with self.assertRaises(MovementError) as ctx:
            self.drone.move("forward", 50)
        self.assertIn("error Not joystick", str(ctx.exception))

    def test_motion_commands_are_not_retried(self):
        self.tello.responses["forward 50"] = None
        self.drone.MOVE_TIMEOUT = 0.2
        with self.assertRaises(CommandTimeoutError):
            self.drone.move("forward", 50)
        self.assertEqual(self.tello.received.count("forward 50"), 1)

    def test_argument_validation(self):
        with self.assertRaises(ValueError):
            self.drone.move("sideways", 50)
        with self.assertRaises(ValueError):
            self.drone.move("up", 10)
        with self.assertRaises(ValueError):
            self.drone.rotate("cw", 0)
        with self.assertRaises(ValueError):
            self.drone.go(5, 5, 5, 50)
        with self.assertRaises(ValueError):
            self.drone.set_speed(5)
        self.assertEqual(self.tello.received, ["command"])

    def test_speed(self):
        self.drone.set_speed(40)
        self.assertEqual(self.drone.get_speed(), 100)
        self.assertEqual(self.tello.received[1:], ["speed 40", "speed?"])

    def test_send_rc_clamps_and_does_not_wait(self):
        start = time.monotonic()
        self.drone.send_rc(150, -150, 20.6, 0)
        self.drone.hover()
        self.assertLess(time.monotonic() - start, 0.5)
        time.sleep(0.2)
        self.assertEqual(self.tello.received[1:], ["rc 100 -100 21 0", "rc 0 0 0 0"])

    def test_late_response_is_not_mistaken_for_next_command(self):
        # "speed 40" is answered after its timeout, the stale "ok" must not
        # be returned as the answer to "speed?"
        self.tello.delays["speed 40"] = 0.4
        with self.assertRaises(CommandTimeoutError):
            self.drone.send_command("speed 40", timeout=0.2)
        time.sleep(0.4)
        self.assertEqual(self.drone.get_speed(), 100)

    def test_keepalive_pings_when_idle_and_does_not_block_commands(self):
        self.drone._command_handler._keepalive_interval = 0.2
        time.sleep(2.5)
        self.assertGreaterEqual(self.tello.received.count("command"), 2)
        self.drone.move("up", 30)  # Would hang if the keep-alive held the lock


if __name__ == "__main__":
    unittest.main()
