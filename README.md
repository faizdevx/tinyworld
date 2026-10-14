# TinyWorld

Describe a world in a sentence. TinyWorld researches it, writes it up as a world
bible, and runs it with autonomous agents. You watch, intervene as a god, skip
years, and fork history to see what else could have happened.

> "What if India never had Jio internet in 2016? Lucknow, Uttar Pradesh."

That becomes a city of a dozen named people with goals, fears and secrets,
institutions and factions, scarce things and live tensions. Then it runs.

<p>
<img src="docs/images/v3-lucknow-bible.jpg" width="49%" alt="A world built from one sentence: what changes, and why">
<img src="docs/images/v3-lucknow-world.jpg" width="49%" alt="People moving between the lanes of the old city">
</p>
<p>
<img src="docs/images/v3-person.jpg" width="49%" alt="A person: wants, plan, what they believe">
<img src="docs/images/v3-change.jpg" width="49%" alt="Changing the world in a sentence">
</p>

## How well it works

Read this first. It says what has been seen working on a real model, what has
only been shown on scripted stand-ins, and what is not built.

| Part | Status | Evidence |
|---|---|---|
| Premise to world bible | **Works live**, slow | Lucknow 2016 on OpenRouter: 12 places, 13 people, 6 factions, 28 model calls, about 10 minutes. Gandhi premise: premise, divergence and 7 sources worked; stopped at drafting when the account ran out of credit. |
| Seeding and the event log | **Works** | Invariants held over every run; a recorded run replays to an identical log with **0** model calls (54 of 54 events). |
| Agents deciding, Game Master, god command | **Passes smoke tests live**, not seen in a long live run | One real call per step validated against the real schema on three models. A complete live run was cut short by an expired key. |
| Days that run on routine | **Works with scripted agents** | Offline Berlin demo, 39 simulated hours, 10 people: model calls per simulated day 1,140 down to 460 to 530. |
| Conversations and promises | **Works with scripted agents** | 22 of 22 promises kept over four offline runs (1 of 10 before the fix). This shows the mechanism, not that a model keeps promises. |
| Knowledge and projects | **Works, covered by tests**, never seen live | A person can start a project, a discovery needs its foundations, finishing teaches the workers. |
| Real people in a bible | **Not guarded** | The Lucknow bible included real, named executives as characters. Nothing stops this yet. |
| Persona change, year-by-year skips, factions that decide, outside news | **Not built** | Planned in [docs/V3_PLAN.md](docs/V3_PLAN.md). |

The honest summary: **building a world from a sentence works on a real model.
Living in it has been verified in pieces, not as one long live run.** Run the
command under [Checking that a model works with it](#checking-that-a-model-works-with-it)
with a funded key to produce that run yourself.

## What you can do with it

Each example says what to type, what you get, and how far it goes.

### 1. "What if India never had Jio internet in 2016? Lucknow."

A counterfactual with a clear place and date.

- **You get:** a bible with three orders of consequence (smartphone growth
  stalls, ride-hailing stays a luxury, UPI lags and cash dominates), research
  from Wikipedia with cited notes, 12 places, 13 people, factions and tensions.
- **Seen live:** all of it, in one run. 28 calls, 277,524 tokens in and 49,530
  out.
- **Extent:** the people came back with empty goals in that run, and some were
  real executives. Both are fixed or flagged since (blank goals now trigger a
  redraft); neither has been re-checked on a live run.

### 2. "1941. Germany never invades the USSR. A town near Berlin."

The built-in reference world: Soviet grain in the goods shed, a baker hiding
flour, a mayor falsifying ration cards.

- **You get:** ten people with conflicting aims, ration scarcity, a party
  informer, a Soviet inspector at the inn.
- **Seen:** offline with scripted agents (this is the prepared world), and in
  tests for genesis. Not judged against a model for how lively it is.
- **Extent:** with no key the page picks this world for any premise that fits
  neither prepared world, and says it was not built from your text.

### 3. "What happens if Gandhi died before independence, will India still get it?"

A question about history, not a setting, with a real, famous person.

- **You get, live:** the premise read, a divergence with consequences, and 7
  research sources. That part ran.
- **Not seen:** the bible. The account had no credit, so section drafting
  stopped at technology.
- **Extent:** a vague question works as a premise on a model that can read it.
  The first attempt failed because one model refuses to run without reasoning,
  and the app reported that as "could not read the premise"; both are fixed.
  Gandhi himself would appear as a character, and there is no guard for that
  yet. Prefer a place and a date: "a district town in Uttar Pradesh, 1946".

### 4. Change the world in a sentence

Type into the Change tab. With a model, any wording; offline, a small fixed
syntax:

| Say | Result |
|---|---|
| `Albert Einstein is born at the bakery` | A newborn with a generated persona, who ages and is promoted to an acting person when old enough |
| `kill Otto Brandt` | The mayor dies; witnesses remember it |
| `move Lena Vogel to Town Hall` | Moved, if there is a way there |
| `skip 6 months` | The chronicler narrates the period; each proposed event is checked before it counts |
| a request that is impossible, unclear, or in the past | A verdict with a reason, or an offer to branch the timeline at that point |

- **Extent:** the god channel is tested end to end and replays exactly. Free
  wording on a real model passed its smoke test; it has not been run at length.

### 5. Fork history and compare

Fork at any moment, make a different change on each branch, skip both forward,
then open the comparison.

- **You get:** the branch tree, a diff of people, things and facts, and a
  chronicle by year with a "why" trace for each entry.
- **Extent:** branches share their parent's log, so a fork is free. The
  comparison is real for scripted runs; how different two model-driven worlds
  become has not been measured.

### 6. Watch ideas and projects (new in v3)

People can start undertakings of their own, and new ideas need foundations.

- **Example from the tests:** a radio transmitter needs radio repair and
  electrical wiring. Nobody can start it without them; a team that has them
  works for months (harder ideas take longer); when it is done the workers know it, and a fact "X worked
  out radio transmitters" is recorded. A rocket motor then becomes possible
  because the transmitter now exists.
- **Extent:** a small graph of ideas (tens of nodes) per world, built from the
  bible's technology section. It limits what can happen; it does not invent
  physics. Not yet seen driven by a real model.

## What changed in v3

People now live a day instead of being asked what to do every hour.

- **Routines.** Anyone with a home and a workplace sleeps at night, gets ready in
  the morning, and works in the day, by rule, with no model call. Work is paid.
  Free hours, and anything important that happens, go back to the model.
- **Long quiet steps.** When everyone is on routine the clock jumps to the next
  boundary in one step, and the shift is paid for all of it.
- **Scenes.** A line said to someone is answered inside the same step, for up to
  four turns. Tone changes how they regard each other.
- **Promises.** A promise made in a scene becomes a commitment with a due time. It
  is part of the person's day: they set out in time. It is kept or broken when
  it falls due, trust moves, and both people remember it.
- **Knowledge, projects, teaching.** See example 6.
- **A run report.** `python -m tinyworld.eval.report --db worlds.sqlite` shows the
  mix of actions, waiting and repetition, why attempts failed, calls per
  simulated day, promises kept and broken.
- **A quieter interface,** a prepared world that fits your words when there is no
  key, and a place to add a key from the page.

Offline Berlin demo, 39 simulated hours, 10 people, before and after:

| | before | after (four runs) |
|---|---|---|
| model calls per simulated day | about 1,140 | 460 to 530 |
| promises kept | 1 of 10 | 22 of 22 |
| waiting / repeating | 5% / 0% | 4% to 8% / 0% |

Ordinary routine lines ("X sleeps") are no longer sent to a model to be scored,
which was most of the memory upkeep. These runs use scripted agents.

## To what extent

| Question | Today |
|---|---|
| How many people? | About 8 to 15 followed closely; thousands more as a background number. Not tested at 100. |
| How long does a world take to build? | About 10 minutes on a hosted fast model. Slow, and it is the longest wait. |
| What does a simulated day cost? | Offline: 460 to 530 model calls per day for 10 people. On a model that is real money; the app shows cost and has a budget cap. Gemini prices are not built in. |
| How long can it run? | Time skips of days to decades, narrated by a chronicler. A year-by-year simulated skip is not built. |
| Is it accurate history? | No. It is a plausible reading, researched from Wikipedia, checked for anachronisms by keyword. Treat it as fiction with a research base. |
| Is it repeatable? | Yes for a recorded run: replay gives an identical event log with no model calls. A new run on a model differs. |
| Does it need a key? | No for the offline demo; yes to build a world from your own words. |

## Running it

```bash
pip install -e ".[llm,dev]"
python -m tinyworld.api.app
```

Open <http://127.0.0.1:8000>. Worlds are kept in `.tinyworld_data/worlds.sqlite`
(set `TINYWORLD_DB` to use another file).

**With a model.** Set one key before starting: `ANTHROPIC_API_KEY`,
`OPENROUTER_API_KEY` or `GEMINI_API_KEY` (`TINYWORLD_PROVIDER` chooses if more
than one is set). Genesis then reads your premise, researches it on Wikipedia,
writes and reviews the bible, and the agents, Game Master, god parser and
chronicler run on the model.

**Without a model** the server runs an offline demo. Genesis picks the prepared
world that fits your words (Lucknow if you mention Lucknow, Jio or India;
Berlin for German or Soviet premises) and says which one it used. A premise that
fits neither gets the Berlin world, and the page says it was not built from your
text. Agents follow simple rules, so this is for trying the application, not for
judging how interesting a world is.

**Adding a key from the page.** The top right shows "Add a model key" when no
model is configured. Pick a provider and paste the key. It is checked with one
small call, then held in the server's memory only: not written to a file, the
database or the log, and gone when the server stops.

**OpenRouter.** Choose models per tier with `OPENROUTER_MODEL_STRONG`,
`_STANDARD`, `_CHEAP`. Hidden reasoning is off by default
(`OPENROUTER_REASONING=on` enables it); it made calls about six times slower
with no benefit here. A model that refuses to run without it is detected and
asked again with low reasoning. Real per-call cost comes from OpenRouter's usage
report. An account with no credit stops the run with a clear error, and `:free`
models are often rate limited upstream.

**Gemini.** Tiers map to `gemini-3.5-flash`, `gemini-2.5-flash` and
`gemini-3.5-flash-lite`; change them with `GEMINI_MODEL_STRONG`, `_STANDARD`,
`_CHEAP`. No Gemini prices are built in, so cost shows as $0 and a budget cap
will not trip until you add prices to the JSON file named by
`TINYWORLD_LLM_CONFIG`.

A rejected key, or no credit, stops the run with an error instead of letting
everyone quietly "wait". Which model each role uses is set in
`tinyworld/llm/router.py`.

### Checking that a model works with it

```bash
python -m tinyworld.llm.smoke --provider openrouter
python -m tinyworld.llm.smoke --prompt "Any question you like"
python -m tinyworld.llm.smoke --only agent god
python -m tinyworld.llm.smoke --list-models
```

It sends the application's real prompts (an agent deciding, the Game Master
adjudicating, a god command, genesis reading a premise), validates each reply
against the real schema, and reports pass or fail, repairs needed, tokens and
time. To run the whole application once on a premise and get a report on it
(genesis, seeding, steps, god commands, a time skip, invariants, anachronisms,
persona judging, and a replay with no model calls):

```bash
python -m tinyworld.eval.scenario --provider openrouter --ticks 16 --skip 6mo \
  --premise "What if India never had Jio internet in 2016? Lucknow, Uttar Pradesh."
```

## What you can do (screens)

- **Genesis.** Watch a premise pass through premise, divergence, research,
  sections, critic and digest. Read the bible, edit any section, see the
  reviewer's findings, then start a timeline.
- **World.** A map of places and people, a feed of what happens, an inspector
  for each person (character sheet, plan, what they believe and whether it is
  true, what they remember, what they cost), and a box for changing the world.
- **Time.** Play, pause, step, or skip days to decades.
- **History.** The branch tree, a comparison of two timelines, the chronicle by
  year with a "why?" trace for each entry, numbers including cost per simulated
  year, an invariant check, and a replay check.

## How it works

The design is in [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) and
the v3 plan in [docs/V3_PLAN.md](docs/V3_PLAN.md). In short:

- **State is a fold over an event log.** Nothing changes the world except an
  event committed through `WorldSession.commit`. Forking a branch copies
  nothing; it reads its parent's log up to the fork point.
- **Models never write state.** Agents propose intents. The Game Master settles
  what it can with rules and asks a model about the rest; either way the result
  is a list of effects from a closed set, applied by deterministic reducers.
- **Every model call is recorded.** A run is journaled and can be replayed from
  the recording with no model calls, producing an identical event log.

```
tinyworld/
  core/      ids, time, state, effects, events, reducers, store, session, branches, causes
  llm/       clients, router, structured calls, trace and replay, ledger, fake, offline
  gm/        verbs, rules, adjudicator, conflicts, perception, master
  agents/    persona, memory, retrieval, beliefs, reflection, planner, routine, agent
  world/     knowledge graph, projects
  genesis/   bible, research, critic, seeding, pipeline
  god/       parser, feasibility, compiler, channel
  sim/       loop, scene, commitments, tiers, scheduler, budget, chronicler, timeskip, replay
  eval/      invariants, anachronism, judge, divergence, metrics, report, scenario
  fixtures/  prepared worlds: berlin, lucknow, toy
  api/       app, hub, runner, views, static/app
```

## Tests

```bash
python -m pytest -q
```

363 tests. Set `TINYWORLD_DEBUG=1` to check every committed event against the
invariants as the tests run; CI does this.

## Results so far

### Lucknow without Jio: one whole run on a real model

OpenRouter, `qwen/qwen3.7-flash` for every tier, reasoning off, Wikipedia
research:

| Stage | Result |
|---|---|
| Premise | Placed in Lucknow, 15 September 2016; divergence recognised as "Jio does not launch" |
| Divergence | Three orders of consequence with confidences, e.g. smartphone growth stalls (90%), Ola/Uber stay luxury (80%), UPI lags and cash dominates (75%) |
| Research | 5 Wikipedia sources fetched and turned into cited notes |
| Bible | 12 places, 13 people, 6 factions, 5 institutions, 7 resources, 5 tensions |
| Review | 4 findings, 1 blocking, after capped redraft rounds; all shown |
| Seeding | 13 people, 12 places, 16 links; one repair, which it reported |
| Invariants | Held over all 63 events |
| Replay | 54 of 54 events reproduced with **0** calls to the provider |
| Cost | 28 calls, 277,524 tokens in / 49,530 out; 604 s wall time |

![The bible's divergence analysis and the reviewer's findings](docs/images/lucknow-bible.jpg)

![Generated key figures](docs/images/lucknow-figures.jpg)

*The people it wrote. Note the empty "Wants / Fears / Secret" lines: see below.*

![The seeded world on the map](docs/images/lucknow-world.jpg)

![History and numbers](docs/images/lucknow-history.jpg)

### What did not work in that run

This run is **not** a demonstration that agents behave well on a real model.

- **The simulation part was not exercised live.** The key expired part-way
  through (HTTP 401) and every later call failed. At the time a failed call
  became "wait", so every person waited and the god commands came back "needs
  clarifying". Those lines are not evidence about the model.
- **The people had no goals.** The model returned empty strings for goals,
  fears and secrets, and nothing noticed.
- **Most of the chronicler's proposals were thrown away.** The model named
  people `karan_verma` rather than `person:karan_verma`.
- **Real people appeared** as characters. Nothing stops this yet.
- **Faction leaders were not among the people.**

### Fixed afterwards, each with a test

- A rejected key or missing credit raises an error instead of becoming "wait".
- Blank list entries are dropped; a person with no goals is a blocking finding
  that triggers a redraft.
- Names and bare slugs are resolved to ids for agents and the chronicler.
- "Undefined resource" findings go to the section that can fix them.
- A model that requires reasoning is asked again with it, and a failed premise
  call reports the provider error instead of "could not be read".
- The offline demo picks the world that fits the premise instead of always
  showing Berlin.

### Gandhi premise, partial live run

OpenRouter, `google/gemini-3.6-flash` as the strong tier, premise typed as
"what happen if gandhi died before independence will india got independece".

| Stage | Result |
|---|---|
| Premise | First attempt failed (the model requires reasoning); read correctly after the fix |
| Divergence | Worked |
| Research | 7 sources |
| Sections | Stopped at technology: HTTP 402, the account had no credit |

Two `:free` models were tried afterwards and were rate limited upstream. No
bible exists for this premise, so nothing is claimed about its quality.

### Checked separately, on real models

One model call per step, validated against the real schema
(`python -m tinyworld.llm.smoke`):

| Model | prompt | agents (3 people) | Game Master | god command | premise parse |
|---|---|---|---|---|---|
| `google/gemini-3.5-flash-lite` via OpenRouter | pass | pass, 0 repairs | pass | pass | pass |
| `qwen/qwen3.7-flash` via OpenRouter | pass | pass, 13 s | pass | pass | pass (reasoning on) |
| `gemini-2.5-flash` (Gemini API) | pass | 2 of 3 people fell back | pass | pass | pass |

The Gemini fallbacks were the missing-prefix bug, fixed since. Turning
reasoning off on `qwen/qwen3.7-flash` took the agent step from 75 s and 4,392
output tokens to 13 s and 593.

### Still to show

One complete run on a real model with a funded key: agents acting from goals,
a god command, a skip with chronicled events, persona judging, and a measured
spread across several runs of the same premise.

## Limits worth knowing

- Long runs on a real model have not been judged. How lively, consistent and
  period-true the worlds are is unmeasured; `POST /api/branches/{id}/judge` and
  the divergence tools exist for that.
- Real, living people can appear as characters. There is no guard yet.
- Research uses Wikipedia's public API only; coverage is shallow.
- The anachronism check is keyword-based.
- The map is a graph on a canvas, not tiles or sprites.
- Building a world is slow, and a long run costs real money.

The previous, rule-based version (`WORLD/`) was removed after its useful ideas
were carried over; see [docs/V1_CONCEPTS.md](docs/V1_CONCEPTS.md). It remains
in the git history.
