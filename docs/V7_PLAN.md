# TinyWorld v7: the living town

v6 made the builders visible. v7 makes the **world** feel alive: residents who
live on their own clocks in a place you can see, who walk into the unknown and
make the map grow, and who come to you, the god, with their problems. Every run
is different. Every run is still recorded.

This plan is phases, not dates. Each phase lists what it builds, where in the
code, the design decisions, and the check that must pass before the next phase
starts.

---

## The direction

**Living town + petitions + lazy generation + multiverse.**

- A tile world that grows when someone walks into the unknown.
- Asynchronous residents with their own clocks, drives and models.
- A podium where residents bring you decisions; the god's powers are tools.
- A newspaper and a follow-camera for watching.
- A "run it 20 times" button that shows the spread of outcomes.
- The v6 build team stays, as the world's creators: always on call, and the
  ones who generate new ground when it is needed.

## The one rule about determinism

**Behaviour is stochastic. Storage is a recording.**

| Kept | Dropped |
|---|---|
| The event log as the only truth | Lockstep ticks where everyone decides from one frozen snapshot |
| Every model call recorded | Seeded randomness that makes runs repeat |
| Replay of a recorded run with no model calls | A fixed order of who acts first |
| Branching and fork-compare | |

Entropy comes from the operating system, not from a seed. Every random draw
that affects the world is written to the journal when it is made, so a replay
reads the draws instead of making them. Two live runs differ; a replay of one
run is identical to it. That is the whole trick, and every phase must keep it.

---

## What exists to build on

| Have | Where | Becomes |
|---|---|---|
| Event log, reducers, closed effects, invariants | `core/` | Unchanged foundation |
| Place graph with travel minutes, perception by edge | `core/state.py`, `gm/perception.py` | Places sit on a tile grid; perception uses distance and sight |
| Tick loop with routine, react, deliberate | `sim/loop.py` | Replaced by per-agent clocks (phase 1) |
| Scenes and promises | `sim/scene.py`, `sim/commitments.py` | Kept, triggered by meeting on the grid |
| Knowledge, projects | `world/` | Kept; projects produce visible buildings |
| God channel (parse, judge, compile) | `god/` | Becomes the god's tools for answering petitions |
| Chronicler, cause graph | `sim/chronicler.py`, `core/causes.py` | Feeds the newspaper and "why" chains |
| Studio: foreman, sessions, decisions, bus | `studio/` | The decision queue for petitions; creators generate land |
| Branches, replay | `core/branches.py`, `sim/replay.py` | The multiverse runs as branches |

---

## Phase 0 — four cheap experiments (go / no-go)

Each is small, built on today's code, and answers one question before the big
changes.

| Experiment | Build | Question it answers | Go if |
|---|---|---|---|
| **Petitions** | Residents get an `ask_god` action; it opens a decision in the studio queue; the answer becomes a memory and a belief | Do residents ask for things that are interesting to answer? | In a live run, at least half of petitions are specific to that person's situation |
| **Chaos dial** | A world rule `chaos` 0..1 that scales the rate and size of chance events | Does randomness make stories, or noise? | Human labels rate runs at 0.5 as more interesting than at 0 |
| **Newspaper** | A narrator writes one edition per simulated day from the log | Is a day of this world readable as a story? | A reader can name what happened without opening the feed |
| **Multiverse x5** | Fork one seeded world 5 times, run each with fresh entropy, compare facts | Is the world varied, or only varied in wording? | Runs differ in who did what, not only in phrasing |

**Exit:** a short report in `docs/V7_EXPERIMENTS.md` with numbers and examples
for all four. If the multiverse runs differ only in wording, stop and fix
drives (phase 5) before building the tile world.

---

## Phase 1 — asynchronous residents, recorded randomness

**Goal:** nobody waits for anybody, and runs differ, without losing replay.

### Clocks instead of ticks

`sim/clock.py` (new)

- Each resident has a `next_wake` time. Sleeping, working a shift or walking
  sets it far ahead; a perceived event can wake them early (salience, already
  built for routines).
- The scheduler pops whoever is due next. Residents due within a short window
  (default 2 simulated minutes) decide **concurrently**, each from the world as
  it is when they start, not from a shared frozen snapshot.
- Every decision is committed through one writer. Before committing, the
  intent is checked against the **current** state with the existing rules and a
  reducer dry run. If the world changed under it (the loaf is gone), the agent
  gets "that is no longer possible: …" and decides again. This is optimistic
  concurrency, and it replaces the conflict grouper for most cases.
- Interruptions: an event addressed to someone, or loud enough to reach them,
  cancels their pending wake and wakes them now.

### Sources of non-determinism

| Source | Where | Recorded as |
|---|---|---|
| Who wakes first in a window | scheduler | journal entry `order` |
| Model sampling | every call (temperature per persona, 0.6–1.0) | the call's reply, already recorded |
| Chance events | `world/chance.py` (new) | journal entry `draw` with value |
| Perception noise (mishearing, partial sight) | `gm/perception.py` | the observation itself |
| Rumour distortion when retold | scenes | the utterance |
| Model per resident (optional) | router | the call's model id |

`core/entropy.py` (new): one function `draw(kind, *, journal) -> float` that
uses `secrets` in a live run and reads the journal in a replay. Nothing else in
the code may call `random` for world-affecting choices; a test greps for it.

### Replay

The journal stores: wake order per window, draws, and the existing call
recording. `sim/replay.py` replays the order and draws, and the calls from the
recording. **Two live runs differ; a replay of either is identical.**

**Tests:** concurrent decisions with a conflict re-decide; replay identity on
an asynchronous run; no unrecorded randomness (static check); interruption
wakes the right person.

**Exit:** a 48-simulated-hour run where no two residents act in lockstep, a
second run from the same start that diverges, and both replay exactly.

---

## Phase 2 — the tile world

**Goal:** the world is a place you can see, and position matters.

### Model

`world/grid.py` (new)

- A chunked grid: chunks of 32×32 tiles, each tile with terrain (`ground`,
  `road`, `water`, `wall`, `floor`, `door`, `field`), and a `place_id` for tiles
  that belong to a building or room.
- Places stay entities, as now. A place gains a footprint (a set of tiles) and
  doors. The existing place graph is derived from adjacency through doors and
  roads, so everything that uses `state.path` keeps working.
- People gain `x, y` (tile) next to `location` (place). Moving is walking a path
  over time.
- New effects: `SetTiles` (a chunk patch), `SetPosition`. Each with a reducer,
  an invariant (positions are on walkable tiles, inside the generated area) and
  tests.

### Movement and sight

- A* over walkable tiles, cached per chunk.
- Walking is a `travel` process: the person advances along the path each wake;
  others can see them on the way and stop them.
- Perception: who is within a sight radius with a clear line (Bresenham across
  walls), and who is within hearing distance (shorter through walls). This
  replaces "same place or connected edge" for people outdoors; indoors, the room
  is still the unit.

### Seeding

Genesis already produces places with links and travel minutes. A layout step
turns them into a grid: districts become regions, roads follow links, buildings
get footprints sized by kind. Deterministic from the bible plus recorded draws.

**Tests:** paths avoid walls; sight is blocked by walls; derived place graph
matches the links; positions stay walkable under random runs.

**Exit:** the Lucknow world laid out on a grid, residents walking real paths,
and a conversation that starts because two people saw each other in a street.

---

## Phase 3 — lazy generation: the map grows

**Goal:** the world is unbounded, and grows differently each run.

- **Fog of war.** Only generated chunks exist. When a resident's path or sight
  reaches an ungenerated chunk, a **generation request** is raised.
- **The creators generate it.** A studio task goes to the cartographer
  (geography) with the bible, the neighbouring chunks and a budget: "what is
  north of the Charbagh stand?". The agent proposes tiles, places and people
  through tools; every proposal is checked by the reducers and the critic's
  mechanical checks before it is committed.
- **Bounds.** A place budget per district, the bible's technology and era, and
  the knowledge graph constrain what may appear. New people arrive as tier 2 and
  are promoted when involved.
- **While waiting.** The resident's path stops at the edge and they do
  something else; nobody walks into nothing.
- **Recorded.** Generated content is ordinary events, so replay does not
  regenerate.

**Tests:** a request fires at the frontier and only once per chunk; generated
content passes the same invariants; a replay does not call the creators.

**Exit:** two runs of the same world have different maps beyond the starting
district, both coherent with the bible.

---

## Phase 4 — petitions: residents come to the god

**Goal:** the god is someone residents talk to, not a text box.

### Residents

- A new action `petition` with `kind` (prayer, request, accusation, plea,
  bargain), `text`, and an optional `offering`. Available to anyone; chosen when
  a drive is badly frustrated, after a loss, or when faith is high.
- The petition is an event at a shrine, temple or the podium place on the grid;
  others may see someone praying.
- Faith is a person attribute that moves with answered and ignored petitions.

### The god

- Each petition opens a decision in the studio queue (`studio/state.py`,
  already built). The bell rings, the petitioner's card shows who they are and
  what led here (the cause chain).
- The god answers with **powers as tools**, compiled by the existing god
  channel: grant (a change in the world), whisper (a dream or voice to one
  person), sign (a public omen), refuse (said aloud), punish, or **ignore**.
- Ignoring is a choice: after a timeout the petition resolves as silence, and
  the petitioner remembers it.
- Consequences are ordinary events: beliefs change, relationships shift, a
  miracle seen by many spreads as a story.

**Tests:** a frustrated resident petitions; each answer type produces the right
effects; silence after the timeout; faith moves; petitions replay.

**Exit:** in a live run, petitions arrive unprompted, and answering one visibly
changes what several people do afterwards.

---

## Phase 5 — drives and stakes

**Goal:** residents want things strongly enough to make trouble.

- **Drives** per person: money, safety, status, belonging, faith, curiosity,
  each 0–100 with a set point from the persona. Frustration (distance from the
  set point) feeds salience, planning and petitions.
- **Persona edges at casting:** every figure gets one strong opinion, one grudge
  and one want that conflicts with someone else's. The critic blocks a cast
  without them (extends the existing goals check).
- **Ownership and building.** Projects (already built) produce visible
  buildings and items on the grid; owners can sell, lose or defend them.
- **Institutions.** Residents can found, join, split and dissolve groups
  (factions and organisations already exist as entities); a group has members,
  a leader, aims and rules it can enforce through its members.
- **Laws.** A group with authority can assert a rule as a fact; the Game Master
  applies it in adjudication.
- **Light economy.** Wages (built), prices as world rules moved by scarcity and
  events, debts as relations with amounts.

**Tests:** drive changes from events; frustration raises petition and conflict
rates; a group is founded and dissolved through effects; a law changes an
adjudication.

**Exit:** a live run where disagreement appears in at least a third of
conversations and at least one institution is founded or broken by residents.

---

## Phase 6 — watchability

**Goal:** someone can follow the world without reading logs.

- **Newspaper.** A narrator agent writes one edition per simulated day:
  headline, three stories, a rumour column, each linked to the events behind it.
  An edition is an item in the world; residents can read it, and believe it.
- **Follow-camera.** Pick a person; the view follows them; their thoughts,
  plan, drives and recent memories are beside the map.
- **Interview.** Talk to any resident in character. Read-only by default: what
  they say comes from their memories and beliefs and changes nothing, unless the
  god chooses to appear to them.
- **Graphs.** Relationships (trust, affinity), rumours (who told whom what), and
  the "why" chain for any event (the cause graph exists).
- **Timeline scrubber.** Drag through the day; the map shows where everyone was.

**Exit:** a reader who only reads three newspapers can say what happened in
those days, checked against the log.

---

## Phase 7 — generations

**Goal:** long arcs: families, legacies, a cast you recognise.

- Ageing, courtship, marriage, birth with inherited traits and aptitudes, death
  by age, illness or violence, inheritance of property and debts.
- Children are tier 2 until old enough; the important ones are promoted.
- **A persistent cast.** People can be saved to a cast library and reappear in
  later worlds, with their history as backstory.
- The time skip simulates years per person (one decision per year per tier-0
  resident) instead of narrating them.

**Exit:** a 30-year skip produces a family tree with three generations, and a
grandchild's choices trace back to a grandparent's in the cause graph.

---

## Phase 8 — the multiverse

**Goal:** non-determinism becomes something you can look at.

- **Run it N times.** From one merged world, start N branches with fresh
  entropy, run each for the same simulated span in parallel (bounded by the
  model budget).
- **Spread view.** For each fact, person and place: in how many runs it holds.
  Who is alive, who leads, which buildings exist, which petitions were made.
  Outcome distributions, not single stories.
- **Pick and continue.** Open any run as the main branch.
- **Divergence metric** (already in `eval/divergence.py`) as a headline number.

**Exit:** 20 runs of one premise produce a spread view where at least some
major outcomes (a death, a founding, a marriage) differ between runs.

---

## Phase 9 — many gods

**Goal:** worlds as a shared space.

- Users with roles: god (full powers), demigod (limited powers and a budget),
  observer.
- An **AI god** with its own goal (for example "make the mill fail"), using the
  same powers, answering some petitions. The human sees its moves in the feed.
- Conflicting divine acts are resolved by the Game Master like conflicting
  intents.

**Exit:** two people and one AI god act in the same world without breaking an
invariant, and residents notice that "the gods disagree".

---

## Phase 10 — cost and scale

Asynchronous residents multiply calls. This phase is what makes the rest
affordable, and parts of it run alongside phases 1 to 5.

- **Three speeds** (built for ticks; carried to clocks): routine by rule, react
  on a cheap or local model, deliberate on the standard model.
- **Per-resident model choice:** most residents on a local open-weight model
  (v4 client), a few important ones on a hosted model.
- **Budgets** per world and per simulated day, shown before a run; the
  scheduler slows down rather than overspending.
- **Batching** of the cheap calls (importance, summaries) per window.
- **Workers:** one process per running world, the event log in Postgres when
  more than one world runs at once.

**Exit:** 50 residents for a simulated week at a stated cost, with the cost
estimate before the run within 30% of the actual.

---

## Phase 11 — evaluation for a world that never repeats

A single run proves nothing when every run differs. Evaluate distributions.

| Metric | How |
|---|---|
| Outcome spread | Fact divergence across N runs (phase 8) |
| Liveliness | Events per resident per day that are not routine |
| Disagreement | Share of conversations with refusal, argument or threat |
| Petition quality | Judged: specific to the person, consequential |
| Coherence | Invariant violations (must be 0), contradictions with the bible |
| Readability | Can a reader reconstruct the day from the newspaper |
| Cost | Calls and money per resident per simulated day |

Judges use a different model family from the residents and are calibrated
against human labels before they are trusted.

---

## Interface

The web studio (v6) gains a second mode, the **Town**:

- A tile renderer (PixiJS) with chunks streamed from the server, fog of war,
  sprites with nameplates and state colours, day and night.
- The podium and bell stay; petitions and the creators' questions share the
  queue.
- Side panels: newspaper, follow-camera, interview, graphs, timeline.
- The protocol (v6) adds `chunk.upsert`, `position` (batched), `petition`
  (a decision kind), `edition.add`.

---

## Order

```
P0 experiments ─► P1 clocks + recorded randomness ─► P2 tile world ─► P3 lazy generation
                         │                               │
                         ├─► P4 petitions ─► P5 drives ──┴─► P6 watchability ─► P7 generations
                         │                                                     │
                         └─► P10 cost (alongside)                 P8 multiverse ┴─► P9 many gods
P11 evaluation grows from P0 onward.
```

## Risks

| Risk | Sign | Response |
|---|---|---|
| Runs differ only in wording | P0 multiverse shows the same events | Drives and edges (P5) before the tile world |
| Cost explodes with async residents | calls per resident per day | three speeds, local models, budgets (P10) early |
| Residents stay agreeable | low disagreement | edges at casting, drives, model diversity |
| Lazy generation drifts from the bible | critic findings on generated chunks | bible constraints, place budgets, the critic on every chunk |
| Optimistic commits thrash | many re-decides per window | shorter windows, rule-resolved simple actions, backoff |
| Petitions become spam | petitions per day per person | cooldowns, a drive threshold, faith cost |
| Replay breaks when something reads unrecorded randomness | replay mismatch | single entropy source and a static check that fails the build |
