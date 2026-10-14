# TinyWorld

A world you describe in a sentence, researched and written up as a world bible,
then run by LLM agents who decide for themselves. You watch, intervene as a god,
skip years, and fork history to see what else could have happened.

> "1941. Germany never invades the USSR. A town near Berlin."

That premise becomes a town of a dozen named people with goals, fears and
secrets, a few thousand background inhabitants, institutions and factions,
scarce flour and sealed Soviet grain in the goods shed. Then it runs.

## Running it

```bash
pip install -e ".[llm,dev]"
python -m tinyworld.api.app
```

Open <http://127.0.0.1:8000>. Worlds are kept in `.tinyworld_data/worlds.sqlite`
(set `TINYWORLD_DB` to use another file).

**With a model.** Set `ANTHROPIC_API_KEY` before starting. Genesis then reads
your premise, researches it on Wikipedia, writes and reviews the bible, and the
agents, Game Master, god parser and chronicler all run on the model.

**Without a model** the server runs an offline demo: genesis returns a prepared
bible for the Berlin premise whatever you type, and agents follow simple rules.
Everything else — the map, god commands in a small fixed syntax, time skips,
forks, history — works the same. It is for trying the application, not for
judging how interesting a world is.

Which model each role uses is set in one place, `tinyworld/llm/router.py`, and
can be overridden with a JSON file named by `TINYWORLD_LLM_CONFIG`.

## What you can do

- **Genesis.** Enter a premise. Watch it pass through premise, divergence,
  research, sections, critic and digest. Read the bible, edit any section,
  see the reviewer's findings, then start a timeline.
- **World.** A map of places and people, a feed of what happens, an inspector
  for each person (character sheet, what they are thinking, their plan, what
  they believe and whether it is true, what they remember, what they cost),
  and a box for changing the world in plain words.
- **God commands** come back with a verdict and a reason: done, done with a
  change, not possible, unclear, or "that is in the past" with an offer to
  branch the timeline there.
- **Time.** Play, pause, step, or skip days to decades. Long skips are told by
  a chronicler period by period; everything it proposes is checked before it
  becomes history.
- **History.** The branch tree, a comparison of two timelines, the chronicle
  by year with a "why?" trace for each entry, numbers including cost per
  simulated year, an invariant check, and a replay check.

## How it works

The design is in [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).
In short:

- **State is a fold over an event log.** Nothing changes the world except an
  event committed through `WorldSession.commit`. Forking a branch copies
  nothing; it just reads its parent's log up to the fork point.
- **Models never write state.** Agents propose intents. The Game Master settles
  what it can with rules and asks a model about the rest; either way the
  result is a list of effects from a closed set of seventeen, applied by
  deterministic reducers.
- **Every model call is recorded.** A run is journaled (ticks, skips, god
  commands, budget changes) and can be replayed from the recording with no
  model calls, producing an identical event log.

```
tinyworld/
  core/      ids, time, state, effects, events, reducers, store, session, branches, causes
  llm/       client, router, structured calls, trace and replay, ledger, fake, offline, embeddings
  gm/        verbs, rules, adjudicator, conflicts, perception, master
  agents/    persona, memory, retrieval, beliefs, reflection, planner, agent
  genesis/   bible, research, critic, seeding, pipeline
  god/       parser, feasibility, compiler, channel
  sim/       loop, step, tiers, scheduler, budget, chronicler, timeskip, schedule, replay
  eval/      invariants, anachronism, judge, divergence, metrics
  api/       app, hub, runner, views, static/app
```

## Tests

```bash
python -m pytest -q
```

Set `TINYWORLD_DEBUG=1` to check every committed event against the invariants
as the tests run; CI does this.

## Limits worth knowing

- The agent, Game Master, chronicler and genesis prompts have been exercised
  against scripted and rule-driven stand-ins, not judged against a real model
  in long runs. How lively, consistent and period-true the worlds are with a
  real model has not been measured yet; `POST /api/branches/{id}/judge` and the
  divergence tools exist for that.
- Research uses Wikipedia's public API. Search results are untested against
  the live service.
- The map is a relaxed graph drawn on a canvas, not tiles or sprites.

The previous, rule-based version (`WORLD/`) was removed after its useful ideas
were carried over; see [docs/V1_CONCEPTS.md](docs/V1_CONCEPTS.md). It remains
in the git history.
