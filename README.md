
# TinyWorld

A small deterministic village simulation built in Python.

TinyWorld models a village as a set of entities and independent systems that interact through a central simulation loop.

> Built incrementally to explore simulation architecture, state management, and testable game logic.

## Current Phase

TinyWorld currently simulates:

- NPCs
- Buildings and shops
- Food and money
- Positions and schedules
- Farming
- Restocking
- Shopping
- Food consumption
- Energy
- Simulation time

The project intentionally avoids AI, pathfinding, weather, seasons, and complex decision-making for now.

---

## Simulation Flow

```mermaid
flowchart TD
    A[Simulation Tick] --> B[Schedule]
    B --> C[Farming]
    C --> D[Restocking]
    D --> E[Shopping]
    E --> F[Needs]
    F --> G[Advance Clock]
````

The current food economy follows:

```text
Farm
  ↓
Village Food
  ↓
Restocking
  ↓
Shop
  ↓
NPC Food
  ↓
Consumption
  ↓
Energy
```

The order of systems is intentional. Each system operates on the state produced by the previous stage.

---

## Architecture

```text
World
 │
 ├── Entities
 │   ├── NPC
 │   ├── Building
 │   ├── Shop
 │   ├── Resource
 │   └── Position
 │
 ├── Systems
 │   ├── ScheduleSystem
 │   ├── FarmingSystem
 │   ├── RestockingSystem
 │   ├── ShoppingSystem
 │   └── NeedsSystem
 │
 └── Simulation
     └── Tick Pipeline
```

Core idea:

```text
State
  ↓
Systems
  ↓
State transitions
  ↓
Next tick
```

World state is kept separate from the rules that operate on it.

---

## Project Structure

```text
tinyworld/
├── WORLD/
│   ├── world.py
│   ├── main.py
│   ├── Buildings/
│   ├── Clock/
│   ├── Economy/
│   ├── Farming/
│   ├── Map/
│   ├── Needs/
│   ├── NPCs/
│   ├── Resources/
│   ├── Restocking/
│   ├── Schedules/
│   ├── Shopping/
│   ├── Simulation/
│   └── Village/
│
├── tests/
├── pytest.ini
└── README.md
```

---

## Example Day

```text
08:00  NPC schedules update
12:00  Farmers produce food
13:00  Food is restocked into the shop
19:00  NPCs buy food
20:00  NPCs consume food and restore energy
00:00  Next day
```

---

## Testing

Tests cover individual systems as well as the complete simulation pipeline.

Run the full test suite:

```bash
pytest -v
```

Run a specific test module:

```bash
pytest -v tests/test_simulation.py
```

The project uses small fake objects such as `FakeWorld` and `FakeClock` for isolated system tests, while integration tests use the real simulation objects.

---

## Running the Simulation

From the project root:

```bash
python -m WORLD.main
```

---

## Design Principles

TinyWorld is being built around a few simple rules:

* Keep entities responsible for their own state.
* Keep larger behavior inside independent systems.
* Use deterministic simulation time instead of real-world time.
* Make state transitions explicit.
* Test business rules before adding more complexity.

The goal is to add complexity through small systems rather than turning the simulation into one giant class.

---

## Roadmap

Planned additions include:

```text
[ ] Work system
[ ] Energy costs
[ ] Better inventories
[ ] Production chains
[ ] More resources
[ ] More buildings
[ ] Events
[ ] Relationships
[ ] Richer NPC decisions
[ ] Pathfinding
```

---

## Status

**Phase 1 — Core simulation architecture**

The foundation is in place. The next iterations will expand the simulation while keeping the systems modular and testable.

````
