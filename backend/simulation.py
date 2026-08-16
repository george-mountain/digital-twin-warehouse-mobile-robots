
import asyncio
import heapq
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


TICK_SECONDS = 0.1
CELL_SIZE = 2.5
COLS, ROWS = 32, 20


class Phase(str, Enum):
    TO_PICKUP = "Pickup pallet"
    TO_PACK = "Deliver inventory"
    RETURNING = "Return empty"
    TO_CHARGE = "Recharge battery"
    CHARGING = "Charging"
    WAITING = "Waiting for traffic"


PICKUPS = [(x, y) for x in range(4, 29, 3) for y in (4, 7, 10, 13, 16)]
PACKING = [(29, y) for y in (4, 8, 12, 16)]
CHARGERS = [(1, y) for y in range(2, 19, 2)]
STAGING = [(3, y) for y in range(2, 19, 2)]


def world(cell: tuple[int, int]) -> tuple[float, float]:
    return ((cell[0] - COLS / 2) * CELL_SIZE, (cell[1] - ROWS / 2) * CELL_SIZE)


def heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


@dataclass
class Robot:
    id: int
    cell: tuple[int, int]
    x: float
    z: float
    rotation: float = 0.0
    speed: float = 0.0
    battery: float = 100.0
    phase: Phase = Phase.RETURNING
    previous_phase: Phase = Phase.RETURNING
    target: tuple[int, int] | None = None
    pickup: tuple[int, int] | None = None
    path: list[tuple[int, int]] = field(default_factory=list)
    carrying: bool = False
    cargo_id: str | None = None
    wait_ticks: int = 0
    completed: int = 0
    dock_ticks: int = 0
    reroutes: int = 0

    def snapshot(self) -> dict[str, Any]:
        destination = world(self.target) if self.target else (self.x, self.z)
        distance = sum(
            math.dist(world(a), world(b)) for a, b in zip([self.cell] + self.path, self.path)
        )
        return {
            "id": f"AMR-{self.id:03d}", "n": self.id, "x": round(self.x, 3),
            "z": round(self.z, 3), "rotation": round(self.rotation, 4),
            "speed": round(self.speed, 2), "battery": round(self.battery, 1),
            "task": self.phase.value, "movement": "charging" if self.phase == Phase.CHARGING else
                ("waiting" if self.phase == Phase.WAITING else "moving"),
            "charging": self.phase == Phase.CHARGING, "carrying": self.carrying,
            "cargo": self.cargo_id, "destination": {"x": destination[0], "z": destination[1]},
            "eta": round(distance / max(self.speed, 1.5), 0), "reroutes": self.reroutes,
        }


class WarehouseSimulation:
    def __init__(self, robot_count: int = 25, seed: int = 42):
        self.random = random.Random(seed)
        self.robots: list[Robot] = []
        self.completed_deliveries = 0
        self.started_at = time.time()
        self.sim_time = 7 * 3600
        self.tick_number = 0
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue] = set()
        self._running = False
        self.set_robot_count(robot_count)

    @property
    def blocked(self) -> set[tuple[int, int]]:
        # Shelf blocks leave wide horizontal cross aisles and vertical travel aisles.
        cells: set[tuple[int, int]] = set()
        for x in range(5, 27):
            if x % 3 != 1:
                for y in range(3, 18):
                    if y not in (5, 9, 14):
                        cells.add((x, y))
        return cells

    def set_robot_count(self, count: int) -> None:
        count = min(100, max(10, int(count)))
        while len(self.robots) < count:
            i = len(self.robots) + 1
            cell = self.random.choice(STAGING + [(2, y) for y in range(1, 19)])
            x, z = world(cell)
            robot = Robot(i, cell, x, z, battery=self.random.uniform(32, 98))
            self.robots.append(robot)
            self._assign_work(robot)
        if len(self.robots) > count:
            self.robots = self.robots[:count]

    def _route(self, start: tuple[int, int], goal: tuple[int, int], robot_id: int) -> list[tuple[int, int]]:
        occupied = {r.cell for r in self.robots if r.id != robot_id}
        frontier: list[tuple[float, tuple[int, int]]] = [(0, start)]
        came: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        cost = {start: 0.0}
        while frontier:
            _, current = heapq.heappop(frontier)
            if current == goal:
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (current[0] + dx, current[1] + dy)
                if not (0 <= nxt[0] < COLS and 0 <= nxt[1] < ROWS) or nxt in self.blocked:
                    continue
                congestion = 7 if nxt in occupied and nxt != goal else 0
                new_cost = cost[current] + 1 + congestion
                if nxt not in cost or new_cost < cost[nxt]:
                    cost[nxt] = new_cost
                    heapq.heappush(frontier, (new_cost + heuristic(nxt, goal), nxt))
                    came[nxt] = current
        if goal not in came:
            return []
        path, node = [], goal
        while node != start:
            path.append(node)
            node = came[node]  # type: ignore[assignment]
        return list(reversed(path))

    def _set_target(self, robot: Robot, target: tuple[int, int], phase: Phase) -> None:
        robot.target, robot.phase = target, phase
        robot.path = self._route(robot.cell, target, robot.id)
        robot.wait_ticks = 0

    def _assign_work(self, robot: Robot) -> None:
        pickup = self.random.choice(PICKUPS)
        robot.pickup = pickup
        robot.carrying = False
        robot.cargo_id = None
        self._set_target(robot, pickup, Phase.TO_PICKUP)

    def _arrive(self, robot: Robot) -> None:
        if robot.phase == Phase.TO_PICKUP:
            robot.carrying = True
            robot.cargo_id = f"BIN-{self.random.randint(1000, 9999)}"
            self._set_target(robot, self.random.choice(PACKING), Phase.TO_PACK)
        elif robot.phase == Phase.TO_PACK:
            robot.carrying = False
            robot.cargo_id = None
            robot.completed += 1
            self.completed_deliveries += 1
            if robot.battery < 25:
                self._set_target(robot, min(CHARGERS, key=lambda c: heuristic(robot.cell, c)), Phase.TO_CHARGE)
            else:
                self._set_target(robot, self.random.choice(STAGING), Phase.RETURNING)
        elif robot.phase == Phase.RETURNING:
            self._assign_work(robot)
        elif robot.phase == Phase.TO_CHARGE:
            robot.phase = Phase.CHARGING
            robot.speed = 0
            robot.dock_ticks = 0

    @staticmethod
    def _angle_delta(target: float, current: float) -> float:
        return (target - current + math.pi) % (2 * math.pi) - math.pi

    def _move_robot(self, robot: Robot, dt: float, reserved: set[tuple[int, int]]) -> None:
        if robot.phase == Phase.CHARGING:
            robot.battery = min(100, robot.battery + 4.5 * dt)
            robot.dock_ticks += 1
            if robot.battery >= self.random.uniform(82, 96) and robot.dock_ticks > 80:
                self._assign_work(robot)
            return
        if not robot.path:
            self._arrive(robot)
            return
        next_cell = robot.path[0]
        occupied = {r.cell for r in self.robots if r.id != robot.id}
        if next_cell in occupied or next_cell in reserved:
            robot.speed = max(0, robot.speed - 4.2 * dt)
            robot.wait_ticks += 1
            if robot.phase != Phase.WAITING:
                robot.previous_phase, robot.phase = robot.phase, Phase.WAITING
            if robot.wait_ticks > 14 and robot.target:
                robot.path = self._route(robot.cell, robot.target, robot.id)
                robot.reroutes += 1
                robot.wait_ticks = 0
            return
        if robot.phase == Phase.WAITING:
            robot.phase = robot.previous_phase
        reserved.add(next_cell)
        tx, tz = world(next_cell)
        desired = math.atan2(tx - robot.x, tz - robot.z)
        delta = self._angle_delta(desired, robot.rotation)
        robot.rotation += max(-2.8 * dt, min(2.8 * dt, delta))
        aligned = abs(delta) < 0.35
        max_speed = 3.4 if robot.carrying else 4.2
        stopping = math.dist((robot.x, robot.z), (tx, tz)) < 0.8
        desired_speed = (1.4 if stopping else max_speed) if aligned else 0.35
        accel = 2.8 if desired_speed > robot.speed else 4.0
        robot.speed += max(-accel * dt, min(accel * dt, desired_speed - robot.speed))
        distance = robot.speed * dt
        remaining = math.dist((robot.x, robot.z), (tx, tz))
        if distance >= remaining:
            robot.x, robot.z, robot.cell = tx, tz, next_cell
            robot.path.pop(0)
        elif remaining:
            robot.x += (tx - robot.x) / remaining * distance
            robot.z += (tz - robot.z) / remaining * distance
        robot.battery = max(0, robot.battery - (0.025 + robot.speed * 0.008) * dt)
        if robot.battery < 16 and robot.phase not in (Phase.TO_CHARGE, Phase.TO_PACK):
            self._set_target(robot, min(CHARGERS, key=lambda c: heuristic(robot.cell, c)), Phase.TO_CHARGE)

    async def tick(self, dt: float = TICK_SECONDS) -> dict[str, Any]:
        async with self._lock:
            self.tick_number += 1
            self.sim_time += dt * 12  # accelerated operational clock
            reserved: set[tuple[int, int]] = set()
            order = list(self.robots)
            self.random.shuffle(order)
            for robot in order:
                self._move_robot(robot, dt, reserved)
            return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        charging = sum(r.phase == Phase.CHARGING for r in self.robots)
        waiting = sum(r.phase == Phase.WAITING for r in self.robots)
        avg_battery = sum(r.battery for r in self.robots) / len(self.robots)
        elapsed_hours = max((time.time() - self.started_at) / 3600, 1 / 3600)
        return {
            "type": "snapshot", "tick": self.tick_number, "serverTime": time.time(),
            "robots": [r.snapshot() for r in self.robots],
            "metrics": {"total": len(self.robots), "active": len(self.robots) - charging - waiting,
                "charging": charging, "waiting": waiting, "completed": self.completed_deliveries,
                "averageBattery": round(avg_battery, 1),
                "throughput": round(self.completed_deliveries / elapsed_hours),
                "simulationTime": int(self.sim_time)},
        }

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=2)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    async def run(self) -> None:
        self._running = True
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        while self._running:
            deadline += TICK_SECONDS
            state = await self.tick()
            for queue in tuple(self._subscribers):
                if queue.full():
                    try: queue.get_nowait()
                    except asyncio.QueueEmpty: pass
                try: queue.put_nowait(state)
                except asyncio.QueueFull: pass
            await asyncio.sleep(max(0, deadline - loop.time()))

    def stop(self) -> None:
        self._running = False
