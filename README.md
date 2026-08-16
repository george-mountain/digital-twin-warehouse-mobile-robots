# Atlas AMR Warehouse Digital Twin System

A real-time 3D fulfillment-center simulation with autonomous mobile robots, dynamic A* routing, traffic avoidance, cargo workflows, battery management, charging, and a live operational dashboard.

[digital_twin_warehouse_robots.webm](https://github.com/user-attachments/assets/0d617680-4b54-4fe4-a70c-e653d89effd2)


## Run with Docker

```bash
make build
```

Open [http://localhost:8000](http://localhost:8000).

Useful commands:

```bash
make logs       # follow application logs
make ps         # container and health status
make restart    # restart the service
make down       # stop and remove containers
make test       # run backend unit tests (requires Python dependencies locally)
make clean      # remove containers and the local image
```

## API

- `GET /api/health` – service and simulator health
- `GET /api/state` – latest full warehouse snapshot
- `PUT /api/simulation/scale` – set fleet size with `{"robots": 10|25|50|100}`
- `WS /ws` – robot and metric snapshots approximately every 100 ms

Interactive API documentation is available at `/docs`.
