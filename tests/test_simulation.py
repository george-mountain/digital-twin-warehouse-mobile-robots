import asyncio
import unittest

from backend.simulation import Phase, WarehouseSimulation


class SimulationTests(unittest.TestCase):
    def test_initial_snapshot(self):
        sim = WarehouseSimulation(25)
        state = sim.snapshot()
        self.assertEqual(state["metrics"]["total"], 25)
        self.assertEqual(len(state["robots"]), 25)
        self.assertTrue(all(0 <= r["battery"] <= 100 for r in state["robots"]))

    def test_supported_scale(self):
        sim = WarehouseSimulation(10)
        for count in (25, 50, 100, 10):
            sim.set_robot_count(count)
            self.assertEqual(len(sim.robots), count)
            self.assertEqual(len({r.id for r in sim.robots}), count)

    def test_all_assignments_are_routable(self):
        sim = WarehouseSimulation(100)
        self.assertTrue(all(r.path for r in sim.robots))
        self.assertTrue(all(r.target not in sim.blocked for r in sim.robots))

    def test_simulation_advances(self):
        sim = WarehouseSimulation(25)
        before = [(r.x, r.z) for r in sim.robots]
        for _ in range(50):
            asyncio.run(sim.tick())
        after = [(r.x, r.z) for r in sim.robots]
        self.assertTrue(any(a != b for a, b in zip(before, after)))
        self.assertEqual(sim.tick_number, 50)

    def test_charging_increases_battery(self):
        sim = WarehouseSimulation(10)
        robot = sim.robots[0]
        robot.phase = Phase.CHARGING
        robot.battery = 20
        asyncio.run(sim.tick())
        self.assertGreater(robot.battery, 20)


if __name__ == "__main__":
    unittest.main()
