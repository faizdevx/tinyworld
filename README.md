<div align="center">

# 🌱 TinyWorld

### A deterministic village simulation built in Python

Simulate a small village where NPCs work, buy food, eat, and move through time
using simple, testable systems.

<br>

![Python](https://img.shields.io/badge/Python-3.14.7-blue?style=flat-square)
![Pytest](https://img.shields.io/badge/Tested%20with-Pytest-green?style=flat-square)
![Dataclasses](https://img.shields.io/badge/Stdlib-Dataclasses-blueviolet?style=flat-square)
![Typing](https://img.shields.io/badge/Stdlib-Typing-blueviolet?style=flat-square)
![Phase](https://img.shields.io/badge/Phase-1-orange?style=flat-square)

<br><br>

<!-- Replace this image with your simulation GIF -->
<img src="hero_img.gif" alt="TinyWorld simulation" width="800">

<br><br>

[Architecture](#architecture) ·
[Simulation](#simulation-loop) ·
[Project Structure](#project-structure) ·
[Run](#running-tinyworld) ·
[Tests](#testing) ·
[Roadmap](#roadmap)

</div>

---

## What is TinyWorld?

TinyWorld is a small deterministic village simulation designed around
**explicit state, independent systems, and predictable simulation time**.

The project is being built incrementally. Each feature is introduced as a
small rule, tested independently, and then connected to the larger simulation.

### Current simulation

```text
NPCs
 ├── Roles
 ├── Homes
 ├── Locations
 ├── Food
 ├── Energy
 └── Schedules

World
 ├── Buildings
 ├── Shop
 ├── Food
 ├── NPCs
 └── Systems

Simulation
 └── Tick pipeline
````

---

## ✨ Current Features

| Area         | Current state                         |
| ------------ | ------------------------------------- |
| 👥 NPCs      | Roles, homes, locations, food, energy |
| 🏠 Buildings | Houses, farm, town hall, shop         |
| 🌾 Farming   | Farmers produce food at the farm      |
| 🏪 Shop      | Stores food and handles purchases     |
| 💰 Economy   | Money transfers and food trading      |
| 🍎 Needs     | NPCs consume food and restore energy  |
| 🕐 Clock     | Deterministic simulation time         |
| 📍 Position  | Coordinates and simple movement       |
| 📅 Schedules | Fixed daily NPC schedules             |
| 🧪 Testing   | Unit tests + integration tests        |

---

# Simulation Loop

Each simulation tick processes the current hour before advancing the clock.

```mermaid
flowchart TD
    A["Simulation.tick()"]
    B["ScheduleSystem"]
    C["FarmingSystem"]
    D["RestockingSystem"]
    E["ShoppingSystem"]
    F["NeedsSystem"]
    G["Clock.tick()"]

    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
    G --> A
```

### Why the order matters

```text
Schedule
   ↓
NPC reaches destination
   ↓
Farming
   ↓
Food enters village storage
   ↓
Restocking
   ↓
Food enters shop
   ↓
Shopping
   ↓
Food enters NPC inventory
   ↓
Needs
   ↓
Energy changes
```

The systems operate on the state produced by the previous stage.

---

# 🌾 Food Economy

The current food flow is deliberately simple:

```mermaid
flowchart LR
    A["🌾 Farm"]
    B["Village Food"]
    C["🏪 Shop"]
    D["NPC Food"]
    E["⚡ Energy"]

    A -->|Produce| B
    B -->|Restock| C
    C -->|Buy| D
    D -->|Consume| E
```

### Current rules

```text
12:00
Farmer at Village Farm
        ↓
Produces 2 food

13:00
Village food
        ↓
5 food transferred to shop

19:00
NPC without food
        ↓
Attempts to buy 1 food

20:00
NPC with food
        ↓
Consumes 1 food
        ↓
Restores 20 energy
```

These fixed rules keep Phase 1 deterministic and easy to test.

---

# 🧭 Architecture

TinyWorld separates **state** from **rules**.

```text
                         WORLD
                           │
          ┌────────────────┼────────────────┐
          │                │                │
       Entities         Resources        Buildings
          │                │                │
          └────────────────┼────────────────┘
                           │
                         SYSTEMS
                           │
        ┌──────────┬───────┼────────┬──────────┐
        │          │       │        │          │
    Schedule    Farming  Restock  Shopping   Needs
        │          │       │        │          │
        └──────────┴───────┴────────┴──────────┘
                           │
                       SIMULATION
                           │
                         CLOCK
```

### Core principle

```text
World
  ↓
Systems
  ↓
State transitions
  ↓
Next tick
```

Entities own their state.

Systems own larger behavioral rules.

The simulation controls the order in which those rules run.

---

# 👥 Core Entities

### NPC

An NPC represents a person in the village.

```text
name
role
money
home
location
food
energy
position
schedule
```

NPCs also expose small state-changing operations such as:

```python
npc.move_to(...)
npc.add_food(...)
npc.consume_food(...)
npc.restore_energy(...)
npc.use_energy(...)
npc.eat(...)
```

Larger behaviors are handled by systems rather than being placed entirely inside
the NPC class.

### Building

Generic physical structure with:

```text
name
building_type
money
```

Examples include:

```text
Village Farm
House 1
House 2
Town Hall
```

### Shop

The General Store adds shop-specific state:

```text
name
money
food
food_price
```

### Resource

Resources represent quantities such as food.

```python
food.add(amount)
food.consume(amount)
```

Resource validation prevents invalid quantities such as negative food.

### Position

NPCs use simple coordinates:

```text
x
y
```

Phase 1 intentionally uses simple movement rather than full pathfinding.

---

# ⚙️ Systems

TinyWorld currently uses small systems with focused responsibilities.

| System             | Responsibility                      |
| ------------------ | ----------------------------------- |
| `ScheduleSystem`   | Applies NPC schedules               |
| `FarmingSystem`    | Produces village food               |
| `RestockingSystem` | Moves village food into the shop    |
| `ShoppingSystem`   | Handles NPC food purchases          |
| `NeedsSystem`      | Handles food consumption and energy |

This keeps individual rules isolated and makes them easier to test.

---

# 🏘️ Example Day

```text
08:00  NPC schedules update
   │
   ▼
12:00  Farmers produce food
   │
   ▼
13:00  Village food → Shop
   │
   ▼
19:00  NPCs buy food
   │
   ▼
20:00  NPCs consume food
   │
   ▼
00:00  Next day
```

The simulation clock is independent of real-world time, so a test can start
directly at a specific hour.

```python
world.clock.hour = 12
```

This makes the simulation deterministic and reproducible.

---

# 📁 Project Structure

```text
tinyworld/
│
├── WORLD/
│   ├── __init__.py
│   ├── main.py
│   ├── world.py
│   │
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
│
├── pytest.ini
└── README.md
```

---

# 🧪 Testing

The project uses both **unit tests** and **integration tests**.

### Unit tests

Individual systems are tested with small controlled environments.

For example:

```text
FakeWorld
FakeClock
NPC
Resource
```

This allows a system to be tested without constructing the entire simulation.

### Integration tests

Integration tests verify that the actual systems work together through the
simulation pipeline.

The idea is simple:

```text
Unit tests
    ↓
Verify individual rules

Integration tests
    ↓
Verify system connections
```

---

# 🚀 Running TinyWorld

Clone the repository and run the simulation from the project root:

```bash
python -m WORLD.main
```

---

# ✅ Running Tests

Run the complete test suite:

```bash
pytest -v
```

Run an individual module:

```bash
pytest -v tests/test_simulation.py
```

Other useful modules include:

```bash
pytest -v tests/test_farming.py
pytest -v tests/test_needs.py
pytest -v tests/test_shopping.py
pytest -v tests/test_restocking.py
```

---

# 📊 Simulation Invariants

The current simulation relies on a few important rules.

### Money conservation

Normal money transfers should satisfy:

```text
money before = money after
```

### Food conservation during restocking

Restocking moves food rather than creating it:

```text
village food before + shop food before
=
village food after + shop food after
```

### Valid state

```text
Food >= 0
Energy <= 100
```

### Determinism

Given the same:

```text
starting state
+ same rules
+ same ticks
```

the simulation should produce the same result.

---

# 🛠️ Development Approach

TinyWorld is intentionally built in small layers:

```text
1. Model state
2. Add a rule
3. Test the rule
4. Connect the rule
5. Test the connection
6. Run the simulation
```

The goal is to increase complexity through **small, testable systems** rather
than a single large simulation class.

---

# 🗺️ Roadmap

### Phase 1

* [x] NPCs
* [x] Buildings
* [x] Resources
* [x] Money
* [x] Position
* [x] Clock
* [x] Schedules
* [x] Farming
* [x] Restocking
* [x] Shopping
* [x] Needs / food consumption
* [x] Simulation pipeline


## Phase 2 — Needs, Energy & Economy ✅

Phase 2 introduced consequences and connected the village systems into a basic resource loop.

### Added
- NPC energy and hunger
- Food ownership and consumption
- Work and energy costs
- Rest and energy recovery
- Farmer productivity based on energy
- Farming and food production
- Shop restocking
- NPC food purchases
- Money transfers and trading
- Deterministic full-day simulation

### Food Flow
```text
Farm → Village Food → Shop → NPC → Eat
```

### Simulation Loop
Schedule
→ Work
→ Farming
→ Restocking
→ Shopping
→ Needs
→ Rest
→ Clock
### Core Feedback Loop
Food shortage
→ Hunger increases
→ Energy decreases
→ Productivity falls
→ Food production decreases
### Testing
Added unit tests for Phase 2 systems
Added a deterministic 24-hour integration test
Full test suite: 76 tests passed

## Phase 3 — NPC Relationships & Memory ✅

Phase 3 introduced persistent social state to NPCs.

### Added
- NPC relationships with bounded values from -100 to +100
- NPC memories with day, hour, event, and importance
- Bounded memory storage
- SocialSystem for basic NPC interactions
- Interactions increase relationships
- Interactions create memories
- Social state persists across multiple days

### Social Flow
```text
NPCs share location
→ interaction
→ relationship changes
→ memory created
→ state persists
```

### Testing
Added relationship unit tests
Added memory unit tests
Added social interaction tests
Added multi-day social persistence integration test
Full test suite passes


## Phase 4 — Goals & Decision Making 

Phase 4 adds a deterministic AI decision layer for NPC behavior.

### Added

- Goal-based NPC behavior
- Candidate action selection
- Deterministic utility scoring
- DecisionSystem for choosing actions
- AgentSystem for central NPC decision execution
- ActionExecutor for applying chosen actions
- Decision-aware eating, shopping, working, sleeping, and socializing
- Schedule influence on decisions
- Relationship influence on social decisions
- Memory influence on social decisions
- Decision debugging with action scores
- Multi-day social behavior persistence

### Decision Flow

```text
NPC State
   ↓
GoalSystem
   ↓
Candidate Actions
   ↓
DecisionSystem
   ↓
Utility Scores
   ↓
Chosen Action
   ↓
ActionExecutor
   ↓
World State
   ↓
Next Tick

```

## Phase 5 (turns TinyWorld into a feedback-driven simulation)

## What was added

- World events and event logging
- Work attendance and productivity effects
- Dynamic food pricing
- Price-aware NPC decisions
- Cooperation and conflict
- Reputation and relationship changes
- Cascading consequences
- Seeded randomness
- Environmental events, starting with drought
- 72-hour multi-day emergence tests
- Same-seed reproducibility and different-seed variation

## Core Loop

```text
Decisions
   ↓
Actions
   ↓
World Changes
   ↓
New Conditions
   ↓
New Decisions
```
## Phase 6

### Cognition, Planning & Long-Term Goals

Phase 6 adds continuity to NPC behavior. Instead of deciding only what to do right now, NPCs can pursue goals across multiple ticks and days.

What Phase 6 Adds

Persistent goals with priorities, deadlines, and progress

Multi-step plans and plan execution

Action preconditions and effects

Planning, interruption, and replanning

Beliefs and perception

Memory retrieval

Personality parameters and personality-aware utility

Long-term goals

Multi-day agent trajectories

### agent Flow
```
World State
    ↓
Perception
    ↓
Beliefs
    ↓
Long-Term Goals
    ↓
Plan
    ↓
Decision
    ↓
Action
    ↓
Consequences
    ↓
Memory / Learning
    ↓
Updated Internal State
``` 

Tests: 271 passed

Phase 6 keeps Python deterministic and reality-authoritative while giving NPCs persistent internal state and multi-step behavior.

