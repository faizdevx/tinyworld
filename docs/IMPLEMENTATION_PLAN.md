# TinyWorld v2 — Implementation Plan

Target: a browser app where a text premise becomes a researched world, LLM agents live in it
on their own, a god user changes it in free text, and any point in time can be forked.

This plan is written against the code at commit `fa672ee` (476 tests passing on Python 3.14).

---

## 1. What the current code actually is

Findings from reading the repo, each of which shapes a decision below.

| # | Finding | Where | Consequence for v2 |
|---|---|---|---|
| 1 | The proposal → validate → resolve → consequence pipeline is sound, but its vocabulary is closed and hardcoded to one village: `shop`, `Food`, `"Village Farm"`, `"General Store"`. | `WORLD/Events/engine.py` | Keep the pipeline shape. Replace the vocabulary with a generic effect set. |
| 2 | State is a mutable object graph. The event log is a list appended after mutation. It is a journal, not the source of truth. | `WORLD/world.py`, `Events/event_log.py` | Cannot replay or fork from it. v2 needs real event sourcing. |
| 3 | Agents are utility scoring over a 12-value `ActionType` enum. No LLM, no randomness in cognition. | `AI/decision.py`, `AI/utility.py`, `AI/brain.py` | Cognition is replaced, not extended. |
| 4 | God interventions have two paths. Seven operations go through the event engine. `UPDATE`, `CHANGE_ENVIRONMENT`, `CHANGE_RULE` and `ADVANCE_TIME` mutate state directly with no event. `_create`, `_remove`, `_move`, `_trigger_event` and `_change_resource` in `InterventionEngine` are unreachable. | `Interventions/engine.py` | In v2 every god action is an event. No side door. |
| 5 | Checkpoint restore is lossy: memories, beliefs, relationships, `home`, `food`, and event day/hour are dropped. | `app.py::_restore_world`, `Observatory.build_checkpoint` | Checkpoints become snapshot + event tail, so nothing is hand-serialized. |
| 6 | Space is a hardcoded seven-pair distance table. | `AI/observation.py::LOCATION_DISTANCES` | Replace with a generated location graph. |
| 7 | Time is `day` + `hour` counters starting at day 1. No calendar. | `Clock/clock.py` | A 1941 world needs real dates and variable step size. |
| 8 | Genesis takes a pre-filled `WorldScenario` and emits `NPC 1..N`, all `villager`. | `Genesis/generator.py` | Replaced by the LLM pipeline. `WorldScenario` fields survive as part of the bible schema. |
| 9 | The private-reality layer is real and worth keeping: `Observation` (type, distance, confidence, attention limit), `Message` with `claims`, `Belief` with `source` and `origin_type`, and `Observatory.compare_beliefs`. | `AI/observation.py`, `Communication/`, `Observatory/` | Port these concepts nearly as they are. |
| 10 | Memory retrieval already scores lexical + importance + recency + relationship + goal, and its docstring says the backend is meant to be swapped. Memory is capped at 50, FIFO. | `AI/memory_retrieval.py`, `NPCs/npc.py` | Keep the weighted-score design. Swap lexical for embeddings, FIFO for compaction. |
| 11 | The server holds one global world, ticks on a thread every second, and the UI polls with `setInterval`. `POST /api/interventions` touches the world without taking the lock. | `WORLD/app.py`, `static/app.js` | New async runner, WebSocket push, one writer per branch. |
| 12 | `receive_message` stamps every communication memory with `day=1, hour=0`. `_observe_event` uses `event.target` as the event's location. | `NPCs/npc.py`, `AI/observation.py` | Not worth fixing in place. v2 events carry an explicit `location_id` and `sim_time`. |
| 13 | No dependency manifest. | repo root | Add `pyproject.toml` first. |

**Strategy that follows:** build v2 as a new package `tinyworld/` next to `WORLD/`. Do not
refactor `WORLD/` in place. Findings 1, 2, 3, 6 and 7 mean nearly every module would change
at once, and the 476 tests assert the exact behaviour being removed. `WORLD/` stays frozen and
green as the v1 reference until v2 reaches parity on the features worth keeping, then it is
deleted in one commit.

This replaces the earlier "move old cognition into `legacy/`" idea. The whole of `WORLD/` is
the legacy package.

---

## 2. Architecture

```
            premise                         god text
               │                               │
        ┌──────▼──────┐                 ┌──────▼──────┐
        │   Genesis   │                 │ God channel │
        │  pipeline   │                 │ parse→check │
        └──────┬──────┘                 └──────┬──────┘
               │ seed events                   │ god events
               ▼                               ▼
   ┌───────────────────────────────────────────────────────┐
   │                Event log (SQLite, per branch)         │◄── only writer: commit()
   └──────────┬────────────────────────────────▲───────────┘
              │ fold                           │ effects
        ┌─────▼─────┐   observations   ┌───────┴───────┐
        │ WorldState├─────────────────►│  Game Master  │
        └─────┬─────┘                  │ rules + LLM   │
              │                        └───────▲───────┘
              │ perception filter              │ intents
              ▼                                │
        ┌───────────────────────────────────────────┐
        │ Agents: persona · memory · beliefs · plan │
        └───────────────────────────────────────────┘
              all LLM calls ──► llm layer ──► trace + cost ledger
```

Three rules hold the design together:

1. **State changes only through events.** `WorldState` is a pure fold over the log.
2. **LLMs never write state.** They return structured proposals. The Game Master turns an
   accepted proposal into effects from a closed set, and reducers apply those.
3. **Every LLM call is recorded.** Replay reads the recording, so a finished run is exactly
   reproducible even though the live run was not deterministic.

### Package layout

```
tinyworld/
  core/      ids.py time.py state.py effects.py events.py reducers.py store.py branches.py
  llm/       client.py router.py structured.py trace.py ledger.py fake.py embed.py
  gm/        verbs.py rules.py adjudicator.py perception.py conflicts.py
  agents/    persona.py memory.py retrieval.py reflection.py beliefs.py planner.py agent.py
  genesis/   pipeline.py divergence.py research.py bible.py critic.py seeding.py
  god/       parser.py feasibility.py compiler.py
  sim/       loop.py scheduler.py tiers.py timeskip.py chronicler.py budget.py
  eval/      invariants.py anachronism.py judge.py divergence.py
  api/       app.py ws.py routes_*.py runner.py
web/         Vite + TypeScript + PixiJS
tests/v2/
```

---

## 3. Core contracts

These are the interfaces everything else depends on. Fix them in Phase 1 and change them
reluctantly.

### 3.1 World state

```python
class Entity(BaseModel):            # person, building, item, institution, faction, place
    id: EntityId                    # "person:anna_keller"; keeps v1's namespace:name idea
    kind: Literal["person","place","item","org","faction","resource"]
    name: str
    location: EntityId | None       # a place id; None for abstract entities
    attrs: dict[str, JsonValue]     # typed per kind by a schema registry
    inventory: dict[EntityId, int]
    alive: bool = True

class WorldState(BaseModel):
    sim_time: datetime              # real calendar; replaces Clock(day, hour)
    entities: dict[EntityId, Entity]
    edges: dict[tuple[EntityId, EntityId], PlaceEdge]   # travel time, visibility, audibility
    relations: dict[tuple[EntityId, EntityId], Relation]
    facts: dict[FactId, Fact]       # world truths: "grain is rationed", with valid_from/to
    processes: dict[ProcessId, Process]   # long-running efforts with progress and requirements
    rules: dict[str, JsonValue]
    seq: int                        # last applied event sequence
```

`Process` is what makes multi-year arcs possible. "Build a research institute" or "develop a
fission weapon" is a process with requirements (people, materials, prior facts), a progress
value, and an owner. Agents advance it; the Game Master checks the requirements.

### 3.2 Effects — the closed vocabulary

The generalisation of v1's `Consequence.kind`. Reducers exist for exactly these and nothing else.

```
MoveEntity · TransferItem · ChangeQuantity · SetAttr · CreateEntity · RemoveEntity · Kill
SetRelation · AssertFact · RetractFact · StartProcess · AdvanceProcess · EndProcess
Utter (speech/writing with channel + claims) · SetRule · AdvanceTime
```

`SetAttr` is whitelisted per entity kind through the schema registry, the same idea as v1's
`allowed` table in `_validate_updates`.

### 3.3 Event, Intent, Outcome

```python
class Event(BaseModel):
    branch_id: str
    seq: int
    sim_time: datetime
    kind: str                        # "action", "utterance", "god", "system", "chronicle"
    actor: EntityId | Literal["god","system","gm"]
    location: EntityId | None
    effects: list[Effect]
    narration: str                   # human-readable, for the feed
    causes: list[int]                # seqs of events this one follows from
    visibility: Literal["witnessed","public","secret","god_only"]
    trace_id: str | None             # LLM call that produced it, if any

class Intent(BaseModel):
    agent: EntityId
    verb: Verb                       # core verb or "other"
    target: EntityId | None
    args: dict[str, JsonValue]
    text: str                        # what the agent says it is trying to do, and why
    utterance: Utterance | None

class Outcome(BaseModel):
    intent: Intent
    status: Literal["success","partial","failed","impossible"]
    effects: list[Effect]
    narration: str
    reason: str
```

Core verbs with rule-based validation: `move, speak, give, take, trade, use, make, work,
rest, attack, wait, join, leave`. Anything else is `other` and goes to the LLM adjudicator,
which must still answer in effects from 3.2.

### 3.4 Memory and belief

```python
class Memory(BaseModel):
    id: str; agent: EntityId; branch_id: str; created_seq: int; sim_time: datetime
    kind: Literal["observation","utterance_heard","reflection","plan","summary"]
    text: str
    importance: float                # 0..1, LLM-scored at write time
    embedding: bytes
    source_events: list[int]
    confidence: float                # carried from Observation.confidence
    superseded_by: str | None        # set by compaction

class Belief(BaseModel):             # v1's Belief, plus time and evidence
    agent: EntityId; subject: str; predicate: str; value: JsonValue
    confidence: float; source: str | None
    origin: Literal["observation","communication","inference","prior"]
    evidence: list[str]              # memory ids
    as_of: datetime
```

### 3.5 Storage (SQLite)

```sql
worlds(id, premise, created_at, bible_version)
branches(id, world_id, parent_id, fork_seq, name, created_at)
events(branch_id, seq, sim_time, kind, actor, location, payload_json, causes_json,
       visibility, trace_id, PRIMARY KEY(branch_id, seq))
snapshots(branch_id, seq, state_json)
memories(id, branch_id, agent, created_seq, sim_time, kind, text, importance,
         embedding BLOB, source_events_json, confidence, superseded_by)
beliefs(branch_id, agent, subject, predicate, value_json, confidence, source, origin, as_of_seq)
llm_calls(id, branch_id, tick_seq, role, agent, model, request_json, response_json,
          input_tokens, output_tokens, cost, latency_ms, cache_key)
bible(world_id, version, section, content_json)
sources(world_id, id, url, title, fetched_at, text, notes_json)
```

A branch reads its own rows plus each ancestor's rows up to that ancestor's `fork_seq`.
Forking is therefore one `INSERT` into `branches`; nothing is copied. Events, memories and
beliefs all follow the same rule.

---

## 4. LLM layer

| Role | Tier | Used for |
|---|---|---|
| `genesis.*`, `critic`, `god.parse`, `gm.conflict` | strong | Low volume, high consequence. |
| `agent.act` (tier 0), `agent.reflect`, `gm.adjudicate`, `chronicler` | standard | The bulk of interesting behaviour. |
| `memory.importance`, `agent.act` (tier 1), `perception.summarize` | cheap | High volume, low stakes. |

- Tiers map to model ids in one config file, defaulting to `claude-opus-5-5`,
  `claude-sonnet-5-5` and `claude-haiku-5-5`. Nothing else in the codebase names a model.
- Every call goes through `structured.call(role, schema, messages)`: JSON-schema constrained
  output, pydantic validation, at most two repair retries, then a typed fallback
  (for an agent: `wait`; for the adjudicator: `failed` with reason).
- Prompt layout is stable-prefix-first so provider prompt caching applies: system rules →
  bible digest → persona → then the volatile part (memories, observations).
- `FakeLLM` returns scripted or rule-generated responses keyed by role, so the whole
  simulation runs offline in tests.
- `ledger` records tokens and cost per call, per agent, per tier, per branch. `budget.py`
  reads it.
- Embeddings sit behind `embed.py` with a pluggable provider. Default to a small local model.

Check current provider documentation for structured-output, caching and batch details when
implementing `client.py`; the plan does not depend on any one mechanism.

---

## 5. Phases

Each phase lists what to build, what to test, and the condition for moving on. No phase
depends on a later one.

### Phase 0 — Project baseline

Build
- `pyproject.toml` with pinned dependencies and a `tinyworld` package skeleton.
- `tests/v2/` wired into pytest alongside the existing suite.
- CI running both suites.
- A short `docs/V1_CONCEPTS.md` listing what is being carried over (finding 9, 10) so the
  port is deliberate.

Exit: `pytest` runs 476 v1 tests plus an empty v2 suite, green, from a clean install.

### Phase 1 — Event spine

Build
- `core/state.py`, `effects.py`, `events.py`, `reducers.py` per section 3.
- `core/store.py`: append, range read, snapshot write/read, branch-aware queries.
- `core/branches.py`: `fork(branch, at_seq)`, ancestor resolution.
- `core/time.py`: calendar time and step sizes from minutes to years.
- Schema registry for per-kind attributes.

Test
- Property test: for any event sequence, `fold(events)` equals `fold(snapshot + tail)`.
- Fork test: child sees parent events up to `fork_seq` and none after.
- Reducers reject malformed effects without partially applying an event.
- Port the still-meaningful assertions from `test_event_causality.py` and `test_events.py`.

Exit: state is reproducible from the log alone, and a fork diverges without touching its parent.

### Phase 2 — LLM layer

Build
- `llm/client.py`, `router.py`, `structured.py`, `trace.py`, `ledger.py`, `fake.py`, `embed.py`.
- Replay mode: a `ReplayLLM` that serves responses from `llm_calls` by `(branch, tick, role, agent)`.

Test
- Invalid JSON and schema violations trigger repair, then fallback, and never raise into the loop.
- A recorded run replays with the network disabled and produces an identical event log.
- Ledger totals equal the sum of recorded calls.

Exit: one recorded run replays byte-identically offline.

### Phase 3 — Game Master

Build
- `gm/verbs.py` and `gm/rules.py`: deterministic checks for core verbs (co-location,
  possession, reachability, alive, capacity, time cost).
- `gm/adjudicator.py`: LLM adjudication for `other` and for ambiguous core cases. Input is
  the intent, the local state slice and relevant bible rules. Output is an `Outcome`.
- `gm/conflicts.py`: group same-tick intents by location and contested resource, resolve each
  group in one call.
- `gm/perception.py`: port `ObservationSystem`. For each committed event, compute who
  perceives it and how (visual, auditory, hearsay, public), with confidence and an attention
  limit, using graph edges instead of the distance table.
- A hand-written toy world (six places, three people) as a fixture.
- A minimal debug page: event feed + state JSON, served by a first `api/app.py`.

Test
- Impossible intents are rejected by rules without an LLM call.
- An adjudicator response containing an effect outside the vocabulary is refused.
- Perception: an event in a closed room is not observed from the street; a loud one is heard
  next door with lower confidence. Port `test_private_reality.py` cases.

Exit: scripted intents run through the full propose → resolve → commit → perceive path, and
the debug page shows it live.

### Phase 4 — Agents

Build
- `agents/persona.py`: identity, traits, values, goals, fears, skills, and a
  **knowledge boundary** (what this person could know, given era, place, class, education).
- `agents/memory.py`: write path with importance scoring; `retrieval.py` with
  `score = w_rel·relevance + w_imp·importance + w_rec·recency + w_soc·relationship + w_goal·goal`,
  starting from v1's weights with lexical replaced by embedding similarity.
- `agents/reflection.py`: triggered when accumulated importance crosses a threshold; writes
  higher-level memories and updates beliefs.
- `agents/beliefs.py`: belief updates from observations and from utterance claims, with
  source reliability. Port `Message.claims` → `Belief`.
- `agents/planner.py`: a short rolling plan, re-made when an observation contradicts it.
- `agents/agent.py`: one `act()` call returning an `Intent`.
- Memory compaction: periodic merge of old low-importance memories into `summary` memories.
- `sim/loop.py`: the tick loop from section 6, with agents run concurrently.

Test (with `FakeLLM`)
- Memories written only for perceived events.
- A false claim heard from a trusted source becomes a belief that disagrees with world state,
  and `compare_beliefs` reports it.
- Compaction preserves retrieval of high-importance memories.

Evaluate (with a real model)
- Ten agents, a few simulated days. Read the transcripts. Check for persona consistency,
  knowledge-boundary leaks and agreeableness.

Exit: two runs from the same seed world produce visibly different, internally coherent
histories, and no sampled agent uses knowledge outside its boundary.

### Phase 5 — Genesis pipeline

Stages. Each writes its artifact to `bible` or `sources` and can be re-run alone.

1. **Premise parse** → `{period, place, divergence_point, scope, tone, constraints}`.
   If the premise is too thin to place in time and space, return questions instead of guessing.
2. **Divergence analysis** → ordered list of first-, second- and third-order consequences,
   each with a confidence and a rationale.
3. **Research** → search queries from stages 1–2, fetch, extract notes with citations.
   Fetched text is passed as quoted data and never as instructions. Results are cached.
4. **Bible drafting**, one call per section, each grounded in notes plus divergence:
   geography and places, politics and institutions, economy and scarcity, technology level,
   daily life and culture, factions and their aims, key figures, open tensions.
5. **Critic** → findings typed as `contradiction | anachronism | unmotivated_change | gap`.
   Failing sections are redrafted with the findings attached. Capped at three rounds;
   unresolved findings are shown to the user rather than hidden.
6. **Seeding** → location graph, entities, institutions, key-figure personas with knowledge
   boundaries, relations, starting facts, background population statistics. Emitted as
   ordinary `CreateEntity` / `AssertFact` events with `actor="system"`.
7. **Human gate** → the user reads and edits the bible; edits re-run seeding only.

Also build
- `SearchProvider` interface so the search backend is swappable.
- Bible digest: a compact per-topic summary plus an embedding index, which is what agents and
  the Game Master actually receive.

Test
- Schema validation on every stage output.
- Seeding output passes graph checks: connected map, every person has a home and a location,
  no dangling references.
- Critic catches planted contradictions in a fixture bible.

Exit: the Berlin premise produces a bible that passes schema and critic checks, and Phase 4
agents run in the seeded world without changes to agent code.

### Phase 6 — God channel

Build
- `god/parser.py`: free text → one or more typed commands
  (`spawn, remove, modify, move, trigger_event, change_environment, change_rule, advance_time,
  start_process`), which is v1's `InterventionOperation` plus `start_process`. Ambiguous
  references are resolved against current state, or returned as a question.
- `god/feasibility.py`: checks against state and bible. Verdict is
  `apply | apply_adjusted | needs_fork | reject`, always with an explanation.
- `god/compiler.py`: command → events with `actor="god"` and a visibility (v1's
  `GOD_ONLY` / `WORLD`). Spawning a person runs the persona builder with an era-correct
  knowledge boundary.
- Scheduled interventions ("a drought next summer") stored as pending events.
- Retroactive commands return `needs_fork` and, on confirmation, fork at the target time.

Test
- Port the operation coverage from `test_interventions.py` to the new compiler.
- Every god action appears in the event log; there is no direct mutation path (finding 4).
- Contradictory command ("remove X" where X is already dead) is rejected with a reason.

Exit: "Einstein is born in a house in this town" yields a newborn entity, a household, a
persona whose aptitudes are set and whose knowledge is empty, and an explanation that this is
a new person rather than the historical one.

### Phase 7 — Tiers, time-skip, budget

Build
- `sim/tiers.py`:
  - Tier 0 — full agent every tick.
  - Tier 1 — cheap model, acts every K ticks, shorter context.
  - Tier 2 — no individual cognition. Factions and districts are updated by simple
    statistical rules plus a periodic LLM summary.
  - Promotion on god targeting, involvement in a tier-0 event, or rising importance.
    Demotion after sustained inactivity. A promoted entity gets a backfilled persona and
    memory summary consistent with its tier-2 history.
- `sim/scheduler.py`: variable step size. Small steps when tier-0 agents are interacting,
  large steps when nothing is happening.
- `sim/timeskip.py` and `chronicler.py`: for a skip of N months or years, the chronicler
  proposes notable events per period from state, tensions and running processes; the Game
  Master validates each; accepted events are committed with `kind="chronicle"`; affected
  agents receive summary memories; processes advance.
- `sim/budget.py`: per-run and per-agent caps. On approaching a cap, degrade in order:
  lengthen steps, demote agents, pause and ask.
- Partition the Game Master by location so independent areas resolve concurrently.

Test
- A skip never produces an event that violates an invariant (dead actors, missing
  requirements for a process).
- Budget cap is never exceeded by more than one in-flight batch.

Exit: a twenty-year skip finishes inside the configured budget, and an agent promoted
afterwards has a history that matches the chronicle.

### Phase 8 — Application

Backend
- `api/runner.py`: one async task per active branch; the only writer for that branch.
  Replaces the thread and global `APP_STATE`.
- REST: worlds, genesis stages, bible read/edit, branches and fork, run control
  (play, pause, step, speed, skip), god commands, agent inspection, events with filters,
  cause-graph query, metrics, export.
- WebSocket: event stream, tick status, cost updates, genesis progress.

Frontend (`web/`)
- **Genesis screen**: premise input, stage progress, bible reader and editor, critic
  warnings, citations.
- **World screen**: map (location graph laid out in PixiJS, agents as markers), event feed,
  agent inspector (persona, beliefs with truth comparison, top memories, plan, cost),
  god console with verdict display, time and budget bar, branch selector.
- **History screen**: branch tree, two-branch diff, chronicle by year, cause graph, stats.
- Tile-map rendering with sprite packs comes after the graph view works. The model emits
  state only and never draws.

Exit: someone who has not seen the code can enter a premise, approve a bible, watch the
world, issue a god command, skip time, and fork.

### Phase 9 — Evaluation and hardening

Build
- `eval/invariants.py`: no action by the dead, no movement without a path, conserved
  quantities, every event's causes exist and precede it. Runs on every commit in debug mode
  and in CI against `FakeLLM` runs.
- `eval/anachronism.py`: checks utterances and created entities against the bible's
  technology and knowledge sections.
- `eval/judge.py`: sampled persona-consistency scoring.
- `eval/divergence.py`: run one premise N times; measure spread of outcomes and flag
  collapse to the same story.
- Cost per simulated year reported for every run.
- Input hygiene review: research text, god text and agent utterances are always data inside
  prompts.

Then delete `WORLD/` and its tests in a single commit.

Exit: the minimum bar in section 8 is met and measured, not asserted.

---

## 6. Tick loop

```
1. scheduler.next_step(state)          → step size, active agents by tier
2. apply due scheduled events          (god-queued, process completions)
3. for each active agent, concurrently:
       observations = perception.since(agent.last_seq)
       memory.write(observations)      → importance scoring (cheap tier, batched)
       beliefs.update(observations)
       context = retrieval(agent, observations, plan)
       intent  = agent.act(context)    → one LLM call
4. gm.rules.check(intents)             → reject impossible ones without an LLM
5. gm.conflicts.group(intents)         → by location and contested target
6. gm.adjudicate(groups), concurrently → outcomes
7. store.commit(events)                → reducers apply; snapshot every N events
8. reflection for agents past threshold
9. tier-2 update if due; budget check; publish to WebSocket
```

---

## 7. Mapping from v1

| v1 | v2 | Action |
|---|---|---|
| `Events/event.py` `EventProposal`, `WorldEvent`, `Consequence` | `core/events.py` `Intent`, `Event`, `Effect` | Port the shape, generalise the vocabulary |
| `Events/engine.py` validator / resolver / consequence engine | `gm/rules.py`, `gm/adjudicator.py`, `core/reducers.py` | Rewrite |
| `Interventions/models.py` operations and visibility | `god/` command types | Port |
| `Interventions/resolver.py` `namespace:name` targets | `core/ids.py` | Port |
| `Interventions/engine.py` | `god/compiler.py` | Rewrite; single path through events |
| `AI/observation.py` | `gm/perception.py` | Port; graph instead of distance table |
| `Communication/communication.py` | `Utter` effect + `agents/beliefs.py` | Port message types and claims |
| `AI/beliefs.py`, `AI/knowledge.py` | `agents/beliefs.py` | Port and extend |
| `AI/memory_retrieval.py`, `memory_importance.py` | `agents/retrieval.py`, `memory.py` | Keep scoring design; embeddings |
| `AI/reflection*.py`, `experience_reflection.py` | `agents/reflection.py` | Rewrite on LLM |
| `AI/brain.py`, `reasoner.py`, `decision.py`, `utility.py`, `goal_system.py`, `planner.py`, `replanner.py`, `plan_executor.py`, `action*.py` | `agents/agent.py`, `planner.py` | Replace |
| `Genesis/scenario.py` | bible schema | Fields absorbed |
| `Genesis/generator.py` | `genesis/seeding.py` | Replace |
| `Observatory/observatory.py` snapshots, metrics, `compare_beliefs` | `api/` inspection + `eval/` | Port `compare_beliefs`; checkpoints become snapshot + tail |
| `Simulation/rng.py` | `core/` seeded RNG for rule-based parts | Keep |
| `Farming`, `Shopping`, `Restocking`, `Work`, `Rest`, `Needs`, `Schedules`, `Economy`, `Village`, `Cooperation`, `Conflict`, `Social` | Emergent from agents + Game Master, or tier-2 statistical rules | Drop as modules |
| `app.py`, `static/` | `api/`, `web/` | Replace |

---

## 8. Definition of done

- A premise produces a reviewed, editable bible with citations and critic findings.
- A world runs with at least ten distinct tier-0 agents plus a tier-2 background population.
- God commands in free text change outcomes, and each returns a verdict with a reason.
- Time-skip of years works within a budget shown on screen.
- Any past point can be forked and two branches compared.
- Every agent can be inspected: persona, beliefs versus truth, memories, plan, cost.
- Any finished run replays offline to an identical event log.
- Invariants pass in CI.

---

## 9. Risks, in the order they will bite

1. **The effect vocabulary is too small or too large.** Too small and the adjudicator cannot
   express what happened; too large and reducers become unmaintainable. Start with the list
   in 3.2, log every case where the adjudicator wanted something it could not express, and
   review that log before adding an effect.
2. **Cost.** Agents × ticks × calls. The ledger exists from Phase 2 and the scheduler's
   variable step size from Phase 7 is the main lever, more than model choice.
3. **Bland, agreeable agents.** Needs personas with conflicting goals, real scarcity in the
   seeded world, and a Game Master that lets actions fail. Check in Phase 4, not Phase 9.
4. **Pull toward real history.** The model knows what actually happened in 1941–45. The
   bible digest in every prompt, plus knowledge boundaries, plus the anachronism check, are
   the three defences. Expect to tune all three.
5. **Long processes.** Whether "Einstein builds a bomb" can happen depends entirely on the
   `Process` model and the chronicler. This is the least proven part of the design; build a
   thin version in Phase 4 rather than leaving it to Phase 7.
6. **Memory growth and retrieval drift.** Compaction is part of Phase 4 for this reason.
7. **Local embedding model on Python 3.14.** Confirm wheels exist for the chosen library
   before depending on it; otherwise pin an older interpreter or use an ONNX-based embedder.
8. **Quality cannot be unit-tested.** `FakeLLM` tests prove the plumbing. Only the Phase 9
   evaluations and reading transcripts tell you whether the world is any good.
