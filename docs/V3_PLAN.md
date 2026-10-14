# tinyworld v3 — reviewed implementation plan

This document has two parts. Part 1 is a critical review of the first v3 draft:
what it got wrong, what it over-built, and what it missed. Part 2 is the
revised plan, in milestones, each with tasks, files, data shapes, algorithms,
metrics, risks and an exit check.

---

# Part 1 — Review of the first draft

The first draft was a reasonable list of features and libraries. As a plan it
had five structural problems and a set of smaller ones.

## 1.1 Infrastructure first, value last

**Draft:** phases 0–3 migrate to Postgres, LangChain, LiteLLM and LangGraph with
"no behaviour change", before any autonomy work.

**Objection:** the biggest unknown in this project is not storage or
orchestration. It is whether LLM agents in this engine behave like living
people at all. v2 has never had one full live run where agents act, talk and
pursue goals. Spending four phases on plumbing first means building scale for a
behaviour nobody has seen yet. SQLite comfortably handles one world with 50
agents; the bottleneck for months will be model latency and cost, not the
database.

**Decision:** start with a measured live baseline on the current stack, then
build autonomy on SQLite. Migrate infrastructure when a concrete need appears
(multi-user hosting), not before.

## 1.2 Three layers over every model call

**Draft:** LangChain chat models, routed through LiteLLM, wrapped by
`StructuredLLM`, plus a `ReplayChatModel` so LangChain calls stay replayable.

**Objection:** that is three abstractions doing one job. LiteLLM already
unifies providers, cost, fallback and rate limits. LangChain's
`with_structured_output` behaves differently per provider and changes between
versions, and it would sit between our repair loop and the raw reply. Keeping
replay working through LangChain callbacks is fragile. LangGraph does not need
LangChain models: graph nodes are plain async functions and can call
`StructuredLLM` directly.

**Decision:** `StructuredLLM` stays the only entry point. Under it, one client:
LiteLLM. No LangChain chat models. Agent tool use is done through a portable
structured schema (`{"tool": ..., "args": ...}` or `{"final": ...}`) that works
on weak models and replays like any other call.

## 1.3 LangGraph in the wrong place

**Draft:** the tick loop becomes a LangGraph `TickGraph` with `Send` fan-out and
a Postgres checkpoint after every node.

**Objection:**
- The tick is a short, deterministic pipeline (select → decide → resolve →
  commit). It has no branching worth a graph and no human pause.
- We already have crash recovery: the event log plus the journal reproduce any
  run exactly. A LangGraph checkpoint per node per tick duplicates that and
  writes serialised state many times per tick.
- Parallel `Send` results must be merged in a canonical order or replay breaks.
  That is solvable but is cost without benefit here.

LangGraph is valuable where runs are long, branch on conditions, pause for a
human, and must resume days later: genesis (questions, research fan-out, critic
loop, review), the god channel (preview and confirm), bounded deliberation with
tools, and time skips that fan out per agent-year.

**Decision:** the simulation runtime stays plain asyncio (`TaskGroup` plus a
semaphore). LangGraph runs genesis, god, deliberation and skip, with a SQLite
checkpointer first and Postgres later.

## 1.4 A fixed tick is the wrong time model

**Draft:** keep ticks; add needs, routines and travel on top; tune step size.

**Objection:** a fixed tick makes every agent decide every step. Most of the
time a real person is sleeping, working a shift or walking somewhere. Asking a
model "what do you do now?" for each of them is where the cost goes, and it is
also why "wait" was so common in v2: there was nothing to decide.

**Decision:** move to a **discrete-event scheduler**. Each agent has a
`next_wake` time. Work, sleep and travel set it far ahead. Salient events can
wake an agent early. The scheduler takes everyone due inside a short window,
resolves them together (so conflicts still work), and jumps the clock to the
next wake. This replaces the step policy and makes skips a special case of the
same loop.

## 1.5 One decision mode for every moment

**Draft:** every agent turn is a model call, now with up to 3 tool calls on top.

**Objection:** tool calls per turn multiply latency and cost by two to four
times. Generative-agent systems that work in practice plan coarsely and act
cheaply: a plan is made once, routine steps run without a model, and the model
is called when something relevant happens.

**Decision:** **two-speed cognition**.
- *Routine* — follow the current plan step by rules, no model call.
- *React* — a short call with a small context when a salient event arrives or a
  step is blocked.
- *Deliberate* — a planning call with tools, once per simulated day per agent
  and after major events.

The expected effect is a 5–10× drop in calls per simulated day (see 2.3).

## 1.6 Smaller objections

| Draft item | Objection | Decision |
|---|---|---|
| Sims-style needs (hunger, energy, social…) | Turns drama into chores and spends calls on eating | Needs handled by routine rules; surface only when unmet. Money and safety matter most |
| Supply-and-demand market engine | Agent-based economies are unstable and a deep rabbit hole | Wealth, wages, rent and a few scarce goods; prices are rules moved by events and news |
| Mesa for background population | A framework for what is a few numpy arrays per district | Plain group model (system dynamics) in `world/population.py` |
| Redis, arq, Ray, Sentry, OTel at once | Sprawl for a solo developer; LLM calls are I/O bound, not CPU bound | Postgres `SKIP LOCKED` job table and `LISTEN/NOTIFY` when hosted; no Ray |
| Postgres and SQLite test matrix from day one | Doubles CI time early | Store interface now; Postgres when hosting starts; Postgres tests in CI only |
| "Wait rate under 20%" as the autonomy metric | Easy to game with busywork | Measure goal-linked actions, repetition, disagreement and judged believability |
| LLM judges as truth | Judges are biased and unstable | Calibrate on a human-labelled set before trusting a judge |
| A detailed knowledge graph generated by the model | Hard to generate correctly; easy to get absurd | Coarse graph, 20–60 nodes per world, curated templates per era |
| "Einstein's bomb emerges from ticks" | A 20-year arc happens in skips, which are model-written | Make skips a coarse simulation: per-agent yearly decisions under project and knowledge rules |
| Generated tilesets | Image generation for tiles is unreliable | CC0 asset packs (Kenney, LPC) mapped by place kind; layout from the place graph |
| Sprites and map as the main UI investment | Watching agents walk is not the interesting part | Storylines and narration first; the map second |

## 1.7 What the draft missed

1. **Blandness.** LLM agents drift toward agreeable, helpful, polite behaviour:
   everyone cooperates, plans parties and apologises. A believable world needs
   conflict. This needs design (persona edges, conflicting goals, framing) and
   a metric.
2. **Loops.** Agents repeat the same action or line. Needs a repetition
   detector and forced re-planning.
3. **Context assembly is the core engineering problem.** What goes into each
   prompt, in what order, under what token budget, decides quality and cost.
   The draft treated it as an afterthought.
4. **Prompt injection between agents and from sources.** A web page in
   research, a god command, or one agent's utterance can contain instructions.
   All of them must reach prompts as quoted data, never as instructions.
5. **Prompts as versioned code.** Every prompt needs an id, a version, test
   cases and its hash in every trace.
6. **Watchability.** A user needs to know what is happening without reading
   every event: storylines, headlines and a narrator.
7. **Cost per simulated day as a design number.** Every feature should state its
   effect on calls and tokens per simulated day.
8. **Distillation.** Once good traces exist, a small fine-tuned open model can
   take the routine and react calls at a fraction of the cost.
9. **Model churn.** Model ids change and get retired. Models are named in config
   with capabilities, never in code.

---

# Part 2 — Revised plan

## 2.1 Rules that do not change

1. **The event log is the only truth.** State is a fold over events. Checkpoints,
   caches, indexes and aggregates are derived.
2. **Models propose, reducers decide.** Every change is a typed effect, checked
   by the Game Master, applied by a reducer.
3. **Closed effect vocabulary.** New behaviour adds a named effect with a reducer,
   an invariant and a test.
4. **Replayable.** Every model call goes through `StructuredLLM`, is traced, and
   replays with zero provider calls.
5. **Untrusted text is data.** Utterances, sources, god text and memories enter
   prompts inside quoted, labelled blocks.
6. **Cost is a design number.** Each milestone states calls and tokens per
   simulated day and has a budget that is on by default.
7. **Knowledge boundaries.** A prompt holds only what that person could know.

## 2.2 Architecture

```
Web client (plain JS now, React + PixiJS in M7)
        │ REST + WebSocket
FastAPI ── BranchRunner (asyncio) ─────────────────────────────┐
        │                                                      │
        │  Discrete-event scheduler                            │
        │   due agents in window → Routine | React | Deliberate│
        │   → Game Master (rules → adjudicator → conflicts)    │
        │   → commit events → perception → wake-ups            │
        │                                                      │
        │  LangGraph (long-running, pausable flows):           │
        │   GenesisGraph · GodGraph · DeliberationGraph ·      │
        │   SkipGraph                                          │
        │                                                      │
        └── StructuredLLM (schema, repair, trace, replay, budget)
                 │
              LiteLLM (Anthropic, Gemini, OpenRouter, local vLLM)
Store: SQLite (WAL) + sqlite-vec now → Postgres + pgvector at M6
```

### Libraries, with reasons

| Need | Choice | Why |
|---|---|---|
| Provider access | `litellm` | One API, cost table, fallback, rate limits |
| Long-running flows | `langgraph`, `langgraph-checkpoint-sqlite` then `-postgres` | Interrupts, fan-out, resumable runs |
| Vectors | `sqlite-vec` now, `pgvector` at M6 | Same retrieval query shape on both |
| Embeddings | `fastembed` (`BAAI/bge-small-en-v1.5`, 384 dims) | Local, free, fast enough |
| Research | Tavily or Exa, Wikipedia, `trafilatura` | Real search plus clean text |
| Graphs | `networkx` | Knowledge prerequisites, cause chains |
| Tracing | own `llm_calls` table; `langfuse` optional | Replay needs our table; Langfuse adds a UI |
| Evals | own harness; `promptfoo` for prompt regression | Rubrics we control |
| Fine-tuning (M8) | `unsloth` or `axolotl` for LoRA, `vllm` to serve | Cheap routine and react calls |
| Settings | `pydantic-settings`, `.env` git-ignored | Keys never in code or repo |

## 2.3 Cost model

Every milestone is checked against this model. The figures below are
**illustrative** — fill them in from real ledger data in M0.

```
calls per simulated day =
    N_agents × ( plans_per_day                # deliberate, ~1
               + reacts_per_day               # salient events, ~4–8
               + scene_turns_per_day )        # ~2–6
  + N_scenes × 1                              # scene close
  + GM adjudications (rules handle most)
  + background (news, factions, director)
```

Example, 30 agents:

| Runtime | Calls per simulated day |
|---|---|
| v2 fixed tick, 15-minute steps (96 steps) | 30 × 96 ≈ 2,880 |
| v3 two-speed, event-driven | 30 × (1 + 6 + 4) + overhead ≈ 400 |

Tokens per call target: react ≤ 1.5k in, deliberate ≤ 4k in, scene turn ≤ 2k
in. Multiply by the configured prices to get money per simulated day; the app
shows this estimate before a run.

## 2.4 Milestones

Each milestone ends with a **demo run** on a fixed scenario set and a
benchmark report. Scenario set: Berlin (alt-1941), Lucknow (no Jio 2016), a
toy village, and "Einstein born 1879" (long arc).

```
M0 Baseline ─► M1 A living day ─► M2 Social life ─► M3 Long arcs
                    │                                   │
                    └──────► M4 Genesis & God v3 ◄──────┘
                                     │
                              M5 A wider world
                                     │
               M6 Platform ─► M7 Product ─► M8 Cost & distillation
Evaluation and safety grow in every milestone.
```

---

## M0 — Baseline truth

**Goal:** know how v2 behaves on a real model before changing anything.

**Tasks**
1. `tinyworld/eval/report.py` — a run report generated from the store:
   - decision mix per agent: wait / move / speak / work / other / fallback;
   - GM outcomes: rules, adjudicated, rejected, with reasons;
   - repetition: same intent or same utterance three times in a row;
   - goal linkage: share of decisions whose stated reason mentions a goal,
     plan step or commitment (checked by keyword first, judge later);
   - cost: calls, tokens, money, wall time per simulated hour.
2. `tinyworld/eval/failures.py` — a failure taxonomy. Every fallback, repair,
   rejection and wait is tagged: `schema`, `unknown_id`, `out_of_reach`,
   `no_target`, `nothing_to_do`, `refused`, `provider`.
3. A labelled sample: export 100 random decisions to `tests/labels/m0.jsonl`.
   The user marks each believable / not, with a reason. This calibrates every
   later judge.
4. Run the four scenarios live on one cheap and one standard model, 24
   simulated hours each, with the budget on.
5. Write `docs/BASELINE.md`: numbers, the top five failure tags, example
   transcripts, cost per simulated day.

**Exit:** `docs/BASELINE.md` exists with real numbers. Every later milestone
is compared against it.

**Risk:** the baseline is poor. That is the point — it decides what M1 fixes
first.

---

## M1 — A living day

**Goal:** agents live through a day with purpose: they sleep, work, earn, move,
notice things and react, without the god's help, at a fraction of v2's calls.

### M1.1 Discrete-event scheduler

`tinyworld/sim/clock.py`

```python
class Wake(Model):
    agent: str
    at: datetime          # simulated time
    reason: Literal["plan_step", "arrive", "shift_end", "wake_up",
                    "salient", "commitment", "deliberate"]

class Scheduler:
    def due(self, window: timedelta) -> list[Wake]: ...
    def push(self, wake: Wake) -> None: ...      # replaces an agent's later wake
    def next_time(self) -> datetime | None: ...
```

Loop:
```
while running and budget ok:
    t = scheduler.next_time()
    advance clock to t                       # AdvanceTime effect
    batch = scheduler.due(window=5 minutes)
    intents = await gather(decide(w) for w in batch)   # semaphore-bounded
    sort intents by (agent id)               # canonical order for replay
    events = gm.resolve(intents)             # conflicts within the window
    commit(events)
    for each perceiver of events: maybe_wake(perceiver, salience)
    for each actor: push(next wake from their new plan step)
```

- The god's scheduled events, processes ending and commitments due are wakes
  too, so one queue drives everything.
- The step policy and fixed tick are removed. The UI "run 1 hour" means run
  until the clock passes one hour.
- Waking order and window are part of the journal, so replay is exact.

### M1.2 Two-speed cognition

`tinyworld/agents/mind.py`

```python
async def decide(agent, wake) -> Intent:
    if wake.reason == "deliberate" or not agent.plan.current:
        return await deliberate(agent)          # DeliberationGraph, tools
    step = agent.plan.current
    if wake.reason in ("salient", "commitment") or step.blocked(state):
        return await react(agent, wake)         # one short call
    return routine(agent, step)                 # no model call
```

- **Plan:** made once per simulated day at wake-up, and again after a major
  event. A plan is typed steps:
  ```python
  class PlanStep(Model):
      id: str
      do: Literal["go", "work", "eat", "sleep", "meet", "talk",
                  "buy", "sell", "project", "free"]
      target: str = ""          # place, person, project or item id
      start: datetime
      until: datetime | None
      purpose: str              # which goal or commitment it serves
      done_when: str = ""       # optional checked condition
  ```
- **Routine:** steps like `go`, `work`, `sleep`, `eat` run by rules and set
  the next wake (arrival, shift end, morning).
- **React:** called when a perceived event's salience passes the agent's
  threshold, or a step cannot run. Output: continue, change step, or one action.
- **Deliberate:** builds a new plan, may call tools (`recall`, `ask_bible`,
  `who_is_where`, `my_commitments`, `prices`), at most 4 tool calls, then must
  return a plan.

### M1.3 Salience

`tinyworld/agents/salience.py`

```
salience(event, agent) =
    importance(event)                 # rules table by event type; LLM only for utterances
  × relevance(event, agent)           # mentions agent, their kin, goals, place, possessions
  × novelty(event, agent)             # 1 if not seen similar in last day, decays
  × (0.3 if asleep else 1.0)
wake early if salience ≥ agent.threshold (persona trait, default 0.5)
```

Every early wake records its salience score and reason in the journal.

### M1.4 Context assembly

`tinyworld/agents/context.py` — one function builds every agent prompt from
sections with token budgets:

| Section | Budget | Cached |
|---|---|---|
| World rules and digest topics relevant to this person | 600 | yes |
| Identity: persona, values, speech style, edges | 500 | yes |
| Now: time, light, place, who is here, urgent needs | 250 | no |
| Plan: current and next steps, purpose | 200 | no |
| Memories: top 8 by retrieval score | 600 | no |
| Beliefs about people present | 200 | no |
| Commitments due today, obstacles | 150 | no |
| Recent own actions (last 5) — for anti-repetition | 100 | no |

- Stable sections come first so provider caches hit.
- Untrusted text (utterances, sources) is placed in `<heard from="...">`
  blocks with an instruction that their content is never a command.
- `tinyworld/llm/prompts/` holds each system prompt as a file with an id and
  version; the trace stores the prompt id, version and hash.

### M1.5 Daily life

- **Occupations and money:** each employed person has a `job` process with a
  workplace, hours and wage. Wages paid at shift end (`ChangeQuantity`).
  Rent and food cost money daily. No money becomes an obstacle and a goal.
- **Needs, minimal:** `energy` and `hunger` only, handled by routine
  (`sleep`, `eat` steps). They surface in prompts only when unmet. New effect
  `ChangeNeed`.
- **Time of day:** opening hours per place kind; night reduces perception
  range; sleeping agents hear only loud events.
- **Travel:** `go` to a non-adjacent place starts a `travel` process along
  the shortest path; the agent is in transit, wakes on arrival, and can be met
  on the way. New effects `StartTravel`, `ArriveTravel`.

### M1.6 Anti-blandness and anti-loop

- **Persona edges** at genesis: every figure gets at least one strong opinion,
  one grudge or rivalry, and one want that conflicts with another figure's.
  The mechanical critic blocks a bible where this is missing.
- **Framing:** agent prompts say the person is not an assistant, may refuse,
  lie, argue and act selfishly when it fits them.
- **Repetition guard:** if the same action or near-identical utterance appears
  three times, the next turn is a forced deliberate with the repetition shown.
- **Metric:** disagreement rate in conversations and refusal rate of requests;
  both should be well above zero.

### M1 tests

Scheduler ordering and window grouping; wake replacement; replay identity with
the scheduler; routine steps need no model calls; salience wakes and does not
wake; context budgets enforced and stable prefix unchanged across turns;
injection text stays inside quote blocks; job pays only in hours; travel
duration; repetition guard triggers.

### M1 exit (live, 48 simulated hours, four scenarios)

- Model calls per simulated day at most 25% of the M0 baseline.
- Goal-linked decisions at least 60%; repetition under 5%.
- Every employed agent works its shifts; nobody goes broke without a recorded
  cause.
- Human labels on a new 100-decision sample: believable share higher than M0.

---

## M2 — Social life

**Goal:** people hold real conversations, make and break promises, lie, and
their relationships change because of what happens between them.

### M2.1 Scenes

`tinyworld/sim/scene.py` (plain async loop, not a graph)

- A scene opens when an agent's step is `talk` or `meet`, or a react chooses
  to speak, and at least one other awake person is present.
- Turn order: the opener, then whoever is addressed, then by salience. At most
  6 turns, at most 4 participants speaking; others listen.
- Each turn:
  ```python
  class SceneTurn(Model):
      say: str
      tone: Literal["warm", "neutral", "cold", "angry", "afraid", "joking"]
      to: list[str] = []
      moves: list[Move] = []       # offer, request, accept, refuse, promise,
                                   # threaten, reveal, lie, ask, teach, end
  ```
- `close_scene` turns moves into effects: `Utter` per line, relation changes,
  commitments, transfers both sides accepted, beliefs from reveals and lies.
- Overhearing: perception gives nearby people the lines they could hear, with
  confidence.

### M2.2 Commitments and reputation

- Entity kind `commitment`: parties, what, place, due, status.
  New effects `MakeCommitment`, `ResolveCommitment(kept | broken | released)`.
- Due commitments become wakes. A missed one is marked broken by the scheduler.
- Reputation per observer: derived from kept and broken commitments they saw or
  heard of, discovered lies, help and harm. It shifts trust.

### M2.3 Beliefs about others

- Beliefs gain kinds `wants`, `plans`, `knows`, `feels_about`, formed from
  scenes and observation, with confidence and source.
- A lie creates a false belief linked to the liar. Contradicting evidence
  (observation beats hearsay) exposes it; exposure lowers trust sharply and is
  remembered as important.

### M2 exit (live, 72 simulated hours)

- At least 10 scenes with three or more turns; disagreement in at least 30%.
- At least 5 commitments made, with some kept and some broken.
- Trust changes traceable to scene moves in the cause graph.
- Scene turns per simulated day within the cost model.

---

## M3 — Long arcs

**Goal:** people start projects, ideas spread, and lives unfold over years, so
"a child genius grows up and builds something world-changing" can happen
without a script.

### M3.1 Projects

- Plan step `project` and react/deliberate action `start_project(goal, method,
  place, helpers)`.
- `tinyworld/gm/requirements.py`: the Game Master compiles a proposal into a
  process with typed requirements:
  ```python
  class Requirement(Model):
      kind: Literal["resource", "money", "people", "knowledge", "place", "permit"]
      ref: str            # resource id, knowledge node, place kind, institution
      amount: int = 1
  class ProjectSpec(Model):
      goal: str
      requirements: list[Requirement]
      work_units: int
      outcome: list[EffectTemplate]   # what completion creates
  ```
  Requirements must name defined resources, knowledge nodes and place kinds.
- Progress per work session: `base × aptitude × (1 + 0.5 × helpers) ×
  tool_bonus`. Unmet requirements block progress and become obstacles in the
  agent's plan context.
- Size classes: personal (days), local (months, needs helpers or money), large
  (years, needs an institution). A large project cannot be done alone.

### M3.2 Coarse knowledge graph

`tinyworld/world/knowledge.py`

- 20–60 nodes per world, from era templates (`data/knowledge/1900s.yaml`,
  `2010s.yaml`) adjusted by genesis for the divergence.
- Node: id, label, prerequisites, difficulty 1–5, status (`common`, `rare`,
  `secret`, `undiscovered`), and the actions it unlocks.
- People hold nodes with proficiency 1–3, seeded from education and occupation.
- Discovery: a research project on an `undiscovered` node whose prerequisites
  the team holds. New effect `LearnKnowledge`.
- Spread: `teach` moves in scenes, documents as items carrying nodes, schools as
  institutions, leaks.
- The Game Master rejects actions that need a node the actor lacks. The
  anachronism check uses the graph, not keywords.

### M3.3 Skip as coarse simulation

`tinyworld/graphs/skip.py` (LangGraph)

```
plan_period → [Send agent_year × tier-0 agents] → reconcile → validate
  → life_events → population_step → commit → (next year | done)
```

- `agent_year`: one structured call per tier-0 agent per simulated year:
  what they pursued, which projects advanced, who they grew close to or fell out
  with. The reply is moves and project progress, not prose.
- `reconcile`: resolves conflicts between agents' years with the same rules as
  live play (two people cannot marry the same person; a project cannot exceed
  its work units).
- The chronicler writes the narrative from the committed events afterwards, so
  the story follows the simulation, not the other way round.
- Checkpointed per year, so a 20-year skip can pause and resume.

### M3.4 Life course and persona change

- Reflection may propose one `UpdatePersona` change (goal, value, fear,
  trait) with the events behind it; core values change at most once per
  simulated year.
- Life goals (years) decompose into projects; when one completes or fails, a
  new ambition is generated from persona and circumstance.
- Marriage, birth (child with inherited traits and family relations), illness,
  ageing, death and inheritance through existing effects with typed causes.

### M3 exit

- Live: at least 3 projects started by agents without god input; at least 1
  completed creating a new entity.
- Einstein scenario: god spawns a child in 1879; a 40-year skip and live play
  advance a physics chain through his and others' projects; every step has a
  cause chain; nothing in the graph is unlocked before its prerequisites.
- 20-year skip on Lucknow: marriages, births, deaths, persona changes, all
  invariants pass.

---

## M4 — Genesis and God v3

**Goal:** better worlds, built faster, with the user in control at the right
moments; and a god channel with real powers.

### M4.1 GenesisGraph

`tinyworld/graphs/genesis.py`

```
premise → [interrupt: questions] → divergence → plan_research
  → [Send search × 15–30] → clean → chunk → embed → notes
  → [Send section × 8] → check → critic
  → redraft failing sections only (≤ 3 rounds)
  → knowledge_graph → edges_check → digest_topics
  → [interrupt: user review] → seed
```

- Research results are untrusted: stripped of markup, kept as quoted chunks,
  never as instructions.
- Citations: claims carry source ids; the review screen shows them.
- Required fields: goals, fears, routine, occupation or reason for none,
  relations, persona edges. Faction leaders are figures or marked off-screen.
- **Real-person guard** (`tinyworld/genesis/guards.py`): living real people are
  not acting characters by default — replaced with fictional counterparts or
  kept off-screen. Historical figures are allowed, labelled, and start from
  their documented record. The user can override per world, and the label stays
  visible.
- The offline demo picks the closest canned world and says so.

**Exit:** Lucknow genesis live under 4 minutes on the standard tier, 15+
sources, no blocking findings, no living real people as actors.

### M4.2 GodGraph

`tinyworld/graphs/god.py`

```
parse → judge → compile → preview (throwaway fork, 2 simulated hours)
  → [interrupt: apply | adjust | fork | cancel] → commit
```

Powers:
- **Whisper:** a dream or voice to one person; becomes a memory and belief
  marked as such.
- **Miracle:** a change against normal rules; marked divine in the cause graph.
- **Rules:** `change_rule` values are read by the rules layer, salience,
  prices, needs, perception and prompts. A test asserts each rule key has a
  reader.
- **Arcs:** long instructions become milestones that add pressure
  (opportunities, encounters, resources). They never force an outcome. The arc
  report says which milestones were reached without help.
- **Possess:** the user acts as one agent for a while.
- **Undo:** a fork from just before the command.

**Exit:** the Einstein arc runs from one god command, and the arc report shows
which milestones agents reached on their own.

---

## M5 — A wider world

**Goal:** institutions, factions, prices and outside events shape life in town,
and the user can always tell what is going on.

- **Light economy:** wealth, wages, rent, a few scarce goods with prices as
  rules. Events and news move prices (`SetPrice`). Producers convert inputs per
  shift.
- **Institutions:** roles grant actions (a constable can `arrest`, a clerk can
  `permit`). Projects may need a `permit`.
- **Factions act:** every simulated day, each faction's leader deliberates on
  the faction's situation and issues policies — orders, announcements,
  recruitment, resource moves. Policies become goals and commitments for
  members. Influence follows membership, money and results.
- **News:** a national and world chronicler extends the divergence weekly,
  consistent with the knowledge graph. Items arrive through period channels
  (paper, radio, TV, phone, internet if it exists) and perception delivers them.
  Rumours can distort details; beliefs keep the source.
- **Population:** district groups with count, mood, income and employment,
  stepped with simple rules. Events change them; thresholds produce events.
  A background person is promoted to a named agent when an event needs one.
- **Storylines** (`tinyworld/eval/storylines.py`): cluster events into threads
  by participants and the cause graph; a narrator writes a headline per thread
  per simulated day. This is the "what is happening" view.
- **Director**, off by default: when pacing drops below a threshold, proposes a
  small plausible nudge that passes the same checks as a god command. Every
  nudge is labelled.

**Exit:** a shortage moves prices and changes several agents' plans; a faction
policy changes members' behaviour; outside news changes at least one person's
goals; every simulated day has readable storyline headlines.

---

## M6 — Platform

**Goal:** host it for more than one user.

- Provider layer to LiteLLM fully (if not done in M1), with fallback chains,
  rate limits and fail-fast on long retry delays.
- Postgres with pgvector behind the same `Store` interface; Alembic
  migrations; `tools/migrate_sqlite.py`.
- Jobs: a Postgres table claimed with `SELECT … FOR UPDATE SKIP LOCKED`; one
  worker owns a running branch through an advisory lock.
- Live updates through `LISTEN/NOTIFY` to the API's WebSocket hub.
- LangGraph checkpointer moved to Postgres.
- Auth (`fastapi-users`), worlds owned by users, sharing (view, comment, edit),
  bring-your-own provider key stored encrypted, quotas on worlds, running
  branches and spend.
- Docker images, Compose for one host, backups, health checks; Langfuse and
  structured logs.

**Exit:** two users run worlds at once on one host; a redeploy loses no events;
a migrated v2 world replays identically.

---

## M7 — Product

**Goal:** something people want to watch, steer and share.

- React + Vite + TypeScript client.
- Home with templates; genesis progress with questions and section review forms
  (no raw JSON).
- World view: storyline feed first; map second (PixiJS with CC0 tiles by place
  kind, sprites, movement along travel edges, speech bubbles, day and night);
  person panel (plan, needs, goals, projects, beliefs, relations, memories);
  follow-a-person camera.
- Timeline scrubber with branches and diff; cause-graph explorer; god console
  with preview; arc tracker; cost meter and estimate before a run.
- Feedback buttons on events and lines (believable / not) that feed the
  labelled set.
- Story export: a branch or one person's life as chapters.

**Exit:** a new user creates a world, follows a person through a day, makes a
god change, and exports the story without help.

---

## M8 — Cost and distillation

**Goal:** make long runs cheap.

- Batch APIs for skip years, importance scoring and summaries.
- Semantic cache for repeated GM rulings on identical situations.
- **Distillation:** select routine-react and scene-turn traces that scored well
  with judges and human labels; fine-tune a small open model with LoRA; serve
  with vLLM; route react calls to it; keep deliberate and GM on hosted models.
  Ship only if judged believability drops by less than a set tolerance.

**Exit:** cost per simulated day at least 5× lower than M1 at equal judged
quality.

---

## Continuous — evaluation and safety

Starts in M0 and grows each milestone.

| Metric | Definition | Target from |
|---|---|---|
| Goal-linked decisions | share of decisions whose purpose names a goal, plan step or commitment | M1 |
| Repetition | share of agents with a 3-in-a-row repeated action or line | M1 |
| Wait and fallback | share of decisions that wait without a plan reason, or fall back | M1 |
| Disagreement | share of scenes with a refusal, argument or threat | M2 |
| Commitment integrity | kept / (kept + broken) — should be neither 0 nor 1 | M2 |
| Causal depth | number of chains longer than 5 events per simulated week | M3 |
| Seed divergence | 1 − Jaccard overlap of facts between two seeds | M3 |
| Anachronism leaks | actions or facts that need an undiscovered knowledge node | M3 |
| Believability | human labels; judge agreement with labels before use | M0 |
| Cost | calls, tokens, money and wall time per simulated day | M0 |

- Judges use a different model family than the one that acted, and are only
  trusted after agreeing with the human labels on a held-out set.
- `promptfoo` cases for every prompt; a prompt change must not lower scores.
- Nightly benchmark on the scenario set with a capped key; results tracked over
  time.
- Safety: content limits on generated text, moderation of god commands, audit
  log of god actions, injection tests (a source page and an utterance that try
  to issue instructions must have no effect).

---

## 2.5 Effect vocabulary after v3

v2's 17 effects stay. v3 adds:

| Effect | Milestone |
|---|---|
| `ChangeNeed` | M1 |
| `StartTravel`, `ArriveTravel` | M1 |
| `MakeCommitment`, `ResolveCommitment` | M2 |
| `LearnKnowledge` | M3 |
| `UpdatePersona` | M3 |
| `SetPrice` | M5 |

Projects, births, deaths, marriages, institutions and policies use existing
effects with typed causes.

## 2.6 Top risks

| Risk | Sign | Response |
|---|---|---|
| Agents still bland | low disagreement, everyone helpful | stronger edges, model choice, framing; test on several model families |
| Cost blows up | calls per day above model | raise salience threshold, longer plan steps, cheaper react tier |
| Weak models break schemas | high repair and fallback rates | smaller schemas per call, more rules, react on standard tier |
| Skip years feel scripted | narratives ignore simulation | chronicler writes only from committed events |
| Knowledge graph absurd | odd prerequisites, cheap discoveries | curated era templates, critic checks, difficulty floors |
| Model retired or changed | smoke failures | models only in config; nightly smoke catches it |
| Scope | milestones drag | each milestone ends with a demo and a number; cut features, not exit checks |
