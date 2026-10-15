# TinyWorld v6: the studio

v6 changes what the product is. Until v5 it was a simulation you watched. In v6
it is a **studio**: a visible team of tool-using agents that builds a world for
you, asks you when a call is yours, and lands nothing until you press Merge.
Then the residents live in the world the team built.

This plan says what exists now (v6.0, in this branch), what each later step
adds, and what has to be true before it counts as done.

## What it takes from AgentCraft, and what it does differently

AgentCraft is a Minecraft room around a team of Claude coding agents. Its ideas
are right: a foreman that owns the truth, a view that holds no logic, agents
that use tools in isolated worktrees, a decision queue, and a human merge gate.

| | AgentCraft | TinyWorld studio |
|---|---|---|
| Product | A team doing code work in your repo | A team building a **world**, which then **runs** |
| Output you check | A diff and passing tests | A draft bible, mechanical findings, a reviewer's notes |
| Isolation | Git worktrees | Draft sections, then a new bible version (worlds already branch) |
| After the merge | The work is done | The simulation starts; the same studio watches it |
| Replay | None | Every model call is recorded; a run replays with no calls |
| Models | Claude, Codex | Any: hosted, or open-weight on your own server |
| View | A Minecraft mod (Java, a game install) | A web page; no install |
| Protocol | Typed WebSocket | Typed WebSocket (same shape) |

What is not copied: the game. It is the most expensive part and the least
transferable. What is copied: every principle that makes it feel like a team.

## Architecture

```
 Viewer (web studio)  <--  WebSocket: snapshot + upserts  -->  Foreman
                                                                |
        Studio state (tasks, agents, decisions, memory, feed, draft)  <- persisted
                                                                |
   Task graph --> scheduler --> AgentSession (think, tool, observe, repeat)
                                      |                  |
                                 StructuredLLM       tools: web_search, fetch_page,
                              (record, replay,       read/write_memory, read_draft,
                               budget, repair)       write_section, plan_tasks,
                                      |              ask_user, check/review/request_fix
                          Anthropic | OpenRouter | Gemini | local (vLLM, Ollama) | script
                                                                |
                                  Merge gate --> bible version --> seed --> simulation
```

Rules that do not change:

1. **The foreman is the source of truth.** The view can close and reopen.
2. **Agents propose; the foreman and the reducers decide.** A tool result is a
   fact the foreman produced, never something an agent claims.
3. **Nothing becomes the world without a Merge.**
4. **An agent's state comes from its tools**, not from what it says.
5. **Every model call is recorded.** Studio runs replay too.
6. **Untrusted text is quoted material.** Web pages and other agents' notes
   are never instructions.

## v6.0: the foundation (built, in this branch)

| Piece | Where | State |
|---|---|---|
| Wire protocol: agent, task, decision, memory, feed, goal, snapshot | `studio/protocol.py` | Built |
| Task graph: dependencies, no cycles, ready-set, transitions | `studio/taskgraph.py` | Built, tested |
| State: persisted, restart-safe, decision queue, shared memory, event bus | `studio/state.py` | Built, tested |
| Agent session: tool loop with step cap, repeat guard, error as observation | `studio/session.py` | Built, tested |
| Foreman: cast of 8, parallel scheduling, derived agent state, merge stage | `studio/team.py` | Built, tested |
| Scripted team (no model needed), same protocol | `studio/sim.py` | Built |
| API and WebSocket | `api/studio_routes.py` | Built, tested |
| Studio page: stations, walking agents, task list, decisions, draft, notes | `static/app/js/studio.js` | Built, checked in a browser |

The team: **Marlow** (lead architect: plans, writes the premise and digest),
**Iris** and **Ash** (researchers: search, read, take notes), **Juno**
(cartographer: geography), **Sage** (historian: divergence, politics,
culture), **Otto** (economist: economy, technology), **Wren** (casting:
factions, figures, tensions), **Vera** (critic: reviews and sends sections back).

What the build looks like: Marlow defines the premise and plans a graph of
research, divergence, six independent sections, figures (which need places and
factions), tensions (which need figures), a review and a digest. Researchers
run at the same time, up to three tasks in flight. Writers validate their
section against the real schema and are told exactly what to fix. Vera checks
the draft and sends a section back if needed. Marlow then opens a merge
decision with a summary; **Merge** writes a new bible version, **Request
changes** puts the team back to work with your note, **Reject** changes
nothing.

Honest state: all of this is verified with the scripted team and with
scripted-model tests. **It has not been run with a real model.** The loop is
provider-independent by design, but weak models will need prompt work.

## v6.1: real teams on real models

Goal: the studio works with a hosted model and with an open-weight model, and
you can see what it costs.

- Run the studio on each provider with the existing smoke harness: a `studio`
  step that runs one section task and one research task and validates the result.
- A per-role model map: lead on the strong tier, writers on standard,
  researchers on cheap or local. Config in one file.
- Native tool calling where the provider has it, falling back to the portable
  step schema. Constrained decoding for small models.
- Cost per task and per agent in the nameplate and the feed; a budget per goal
  that pauses the team and asks.
- Retries that change something: a stuck section is retried with the specific
  validation errors, then handed to a stronger model before it is blocked.
- **Exit:** a Lucknow build, end to end, on one hosted and one open-weight
  model, with the draft passing its mechanical checks and a measured cost.

## v6.2: worlds branch like worktrees

Goal: the draft is a real branch of the bible, not a side dictionary.

- Draft sections written onto a draft bible version; the live world untouched.
- A section-level diff against the live version, shown in the merge decision
  (added, changed, removed people and places, not raw JSON).
- Partial merge: accept some sections, send others back with per-section notes.
- Merge is refused if the live world changed since the draft began, and the
  conflict goes back to the team (the same idea as AgentCraft's merge conflicts).
- Re-open a merged world: a new goal ("add a rival faction") builds on the
  current version.
- **Exit:** two goals against the same world, one rebased onto the other.

## v6.3: the residents join the studio

Goal: one view for both stages. The people of the world are agents with tools
too, not one-shot deciders.

- Residents get a session with tools: `recall`, `ask_bible` (bounded by what
  they could know), `who_is_here`, `my_commitments`. Same loop, tighter caps,
  most steps routine.
- A **Town** area in the scene: residents appear at their places, state derived
  from what they do, with the existing map as a layer.
- The studio team can be re-summoned on a running world (the god channel
  becomes "ask the team": add a district, research a rumour).
- **Exit:** build a world, merge it, and watch the residents in the same view
  without changing page.

## v6.4: the scene

Goal: readable at a glance, and pleasant.

- A real scene renderer (sprites, pathfinding between stations, day and night,
  speech bubbles), still a web page.
- A command console: plain text starts a goal, `@name` messages an agent,
  `/answer`, `/status`, `/pause @x`, with completion.
- Agent cards (state, task, recent log, memory, cost), pause, stop, reassign.
- Desktop notification and a title badge when a decision is waiting.
- **Exit:** a stranger can tell, from across the room, who is working, who is
  stuck and who is waiting on them.

## v6.5: the team talks and is steered

- `send_message` between agents, including to a busy one (delivered mid-task).
- Shared memory as a library you can read and edit; per-agent scratch memory.
- Mixed engines in one team (an open-weight researcher, a hosted lead).
- Steering a running task: your message appears in the agent's next step.
- **Exit:** a mid-task correction from the user changes what a writer does,
  visible in the log.

## v6.6: durability and scale

- Studio runs recorded and replayable: a replay of a build reproduces the draft
  with no model calls.
- Postgres and a job queue; one worker per studio; resume by task, not by
  restart of the whole run.
- Many studios at once on one host, with fair sharing of the model.
- **Exit:** kill the process mid-build; it resumes from the last finished task
  with no repeated model calls for finished work.

## v6.7: safety and policy

- A permission policy: tools classified safe, ask, or deny; "Always allow"
  shown with exactly what it covers (a domain, a tool).
- Real-person handling enforced, not only prompted: the casting task cannot
  save a figure flagged as a living public person without the user's yes.
- Spend, step and fetch budgets per goal and per user; an audit log.
- Prompt-injection tests: a search result and a teammate's note that try to
  give orders must change nothing.
- **Exit:** the injection suite passes with every provider tested.

## v6.8: evaluation

Measured on a fixed set of premises, tracked over time:

| Metric | Meaning |
|---|---|
| First-pass rate | Sections accepted by the mechanical checks without rework |
| Rework rate | Fix tasks per section |
| Blocked rate | Tasks that ended blocked |
| Interventions | Questions asked per build (fewer is better, not zero) |
| Time and cost per world | Wall clock and money |
| Draft quality | Judged against a rubric by a different model family, calibrated on human labels |
| Diversity | Spread of names, places and conflicts across premises |

**Exit:** a benchmark that runs on every release and fails on regression.

## Order and risk

```
v6.0 foundation (done) -> v6.1 real models -> v6.2 branches -> v6.3 residents
                                   \-> v6.7 policy       \-> v6.4 scene -> v6.5 talk
                                                v6.6 durability, v6.8 evaluation throughout
```

| Risk | Sign | Response |
|---|---|---|
| Small models cannot drive the tool loop | many capped or failed sessions | per-role model map, constrained decoding, smaller tool sets |
| The team is slow and costly | cost per world, steps per task | step caps, cheaper tiers for research, batch notes |
| Agents ask too much | interventions per build | stricter "decide yourself" prompt, defaults on the question |
| The draft is bland | diversity metric | persona edges at casting, a second-opinion pass |
| The scripted team hides real problems | passing tests, failing live runs | v6.1 exit is a live run, and stays a gate |
