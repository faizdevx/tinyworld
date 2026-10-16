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

## Where v6 stands

Everything below the line is tested with the scripted team and scripted-model
clients. **None of it has run on a real model**, and that is still the one thing
that decides whether v6 works. "Built" means the mechanism exists and is tested;
it does not mean a model drives it well.

| Step | Built, with tests | Not done |
|---|---|---|
| **v6.1** real teams | Model tier per role (lead strong, researchers cheap); a failed task is retried on the strongest tier with the reason added; cost per agent and per goal in the nameplate; a goal budget that pauses the team and asks (Add $1, Add $5, Stop) | A live run on a hosted and an open-weight model; native tool calling; constrained decoding; a `studio` step in the smoke harness |
| **v6.2** worlds branch | The draft is a real bible version (negative, never live) and is tried before the merge: it is seeded in a scratch store and run with rule-driven residents, and the result (steps, events, who acted, invariant problems) is in the merge card; the draft is compared with the live world in words ("3 people added, 1 place removed"); merge some sections and send the rest back with a note; a merge is refused if the live world changed meanwhile, and the team rebases first; a new goal on a built world changes it instead of rebuilding it | Two goals running against one world |
| **v6.3** residents join | Residents who deliberate run a short tool session (look around, recall, check promises and undertakings, then decide), checked by the same rules and replayable; a Town tab lists the seeded world's people; the console and API can ask the team for a change on a built world | The studio and the live map as one view |
| **v6.4** the scene | A tiled studio with rooms, walls and doorways; pixel characters with their own hair, skin and colour, two walking frames, walking A* paths between stations; furniture that shows state (a card per task on the wall, a paper per section on the drafting table, a lit podium when you are needed); speech bubbles; day and night from your clock; a command console (`@name`, `/answer`, `/status`, `/pause`, `/resume`, `/stop`, `/spawn`, `/budget`, `/help`) with name completion; agent cards with pause, stop, message and cost; a title badge and desktop notification when a decision waits | Hand-drawn art; sound |
| **v6.5** talking and steering | `send_message` between agents, delivered at the recipient's next step even mid-task; the same for your messages; editable shared notes; one agent can run on a different model from the rest | Mixed hosted and open-weight teams run live |
| **v6.6** durability | A recorded build (model replies, searches, pages, your answers) replays with no model, no web and no user, and gives the same draft; a stopped build resumes without redoing finished tasks, and a running one restarts on server start | Postgres, a job queue, one worker per studio, fair sharing between studios |
| **v6.7** policy | Fetching a page from a new site asks, with what "Always allow" covers spelled out, and two agents wanting the same site share one question; budgets for spend, calls, searches and pages; an audit log of what the team did outside the draft; tool output cannot close its own quote; a draft flagged for real, living people loses the plain Merge and needs an explicit, logged override | Policy for tools beyond fetch; injection tests against real models |
| **v6.8** evaluation | `python -m tinyworld.eval.studio_bench`: first-pass rate, rework rate, blocked rate, interventions, cost, calls, blocking problems, time, per premise and averaged | Quality judged against a rubric; a nightly run; comparing models |

## The first live runs

The studio has now run on a real model: **NVIDIA Nemotron 3 Super 120B**
(open weights), served by OpenRouter's free tier and reached through the
open-weight client (`--provider local` pointed at an OpenAI-compatible
endpoint), with live web search. Two short probes on the Lucknow premise, one
research task and one section each:

| Probe | What happened | What it exposed | Fixed by |
|---|---|---|---|
| 1 | The researcher searched 15 times, never saved a note, hit the 8-step cap three times, and blocked the build. It asked permission once per new site (4 questions). | No clear end to a research job; a capped session threw its work away; a failed research task held everything up; per-site questions were too many for a person | A step-by-step procedure per job with an explicit end; the step budget shown in every prompt; a capped task that saved its work counts as done; research that never succeeds lets the writers carry on; near-duplicate searches refused; a retry is told what was already tried; one web question per build |
| 2 | Research saved a note and finished; one web question. Then **geography** failed three times: the section JSON was cut off mid-object (`Expecting ',' delimiter`) | One reply could not hold a whole section at 1,500 tokens, and an unreadable reply ended the whole task | Up to 7,000 tokens for a section reply; an unreadable reply costs a step, not the task, with "make it shorter"; writers told to keep lists to eight items |

The account's 50 free requests for the day ran out during probe 2, so the fixes
from probe 2 have not been tried live yet. The ideas behind several fixes come
from AgentCraft's prompts: a numbered procedure for each job, "when done, end
your turn", answered questions kept with the task so a retry does not ask again,
and a hand-over that continues from saved work instead of starting over.

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
