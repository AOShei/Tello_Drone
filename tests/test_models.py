import unittest

from tello_lib import DroneStatus


class StateParsingTest(unittest.TestCase):
    def test_parses_standard_packet(self):
        status = DroneStatus.from_state_string(
            "pitch:1;roll:-2;yaw:3;vgx:4;vgy:5;vgz:6;templ:60;temph:62;tof:10;h:80;"
            "bat:87;baro:164.98;time:7;agx:1.00;agy:-2.00;agz:-999.00;\r\n",
            timestamp=12.5,
        )
        self.assertEqual((status.pitch, status.roll, status.yaw), (1, -2, 3))
        self.assertEqual((status.velocity.x, status.velocity.y, status.velocity.z), (4.0, 5.0, 6.0))
        self.assertEqual((status.temperature.low, status.temperature.high), (60, 62))
        self.assertEqual(status.tof_distance, 10)
        self.assertEqual(status.altitude, 80)
        self.assertEqual(status.battery, 87)
        self.assertAlmostEqual(status.barometer, 164.98)
        self.assertEqual(status.motor_time, 7)
        self.assertEqual(status.acceleration.z, -999.0)
        self.assertEqual(status.timestamp, 12.5)

    def test_extra_leading_fields_do_not_shift_values(self):
        # Tello EDU prepends mission pad data to the packet
        status = DroneStatus.from_state_string(
            "mid:-1;x:0;y:0;z:0;mpry:0,0,0;pitch:1;roll:2;yaw:3;h:50;bat:42;"
        )
        self.assertEqual((status.pitch, status.roll, status.yaw), (1, 2, 3))
        self.assertEqual(status.altitude, 50)
        self.assertEqual(status.battery, 42)

    def test_unparsable_value_defaults_to_zero(self):
        status = DroneStatus.from_state_string("bat:abc;h:30;")
        self.assertEqual(status.battery, 0)
        self.assertEqual(status.altitude, 30)

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            DroneStatus.from_state_string("ok")


if __name__ == "__main__":
    unittest.main()
