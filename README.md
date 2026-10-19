# Multi-Agent Scenario Creator

Type a scenario. A team of AI agents researches it, writes it up as a world, and waits for your
**Merge**. Then the people in that world live in it, on their own clocks, on a map you can see.
Everything runs on **open-weight models you host yourself** (llama.cpp, Ollama, vLLM). No API key
is needed, nothing leaves your machine, and anyone can run it.

> "A small trading town on the Silk Road in 1250, where the road has just closed."

<p>
<img src="docs/images/v7-town-follow.jpg" width="49%" alt="The Town view: a person selected, with plan, wants and memories beside the map">
<img src="docs/images/v7-town-petitions.jpg" width="49%" alt="A resident's petition at the podium, with six powers to answer it">
</p>
<p>
<img src="docs/images/v6-studio-working.jpg" width="49%" alt="The team at work: researchers, writers and the task graph">
<img src="docs/images/v6-studio-merge.jpg" width="49%" alt="The merge card: what would change, a checkbox per section">
</p>

## Run it

You need Python 3.12 or newer and an open-weight instruct model.

```bash
git clone https://github.com/faizdevx/tinyworld && cd tinyworld   # or your fork
pip install -e .

# 1. get llama.cpp (https://github.com/ggml-org/llama.cpp) and any instruct model in GGUF form,
#    for example Qwen2.5-7B-Instruct-Q4_K_M.gguf from Hugging Face.
# 2. start everything and open the browser:
python run_local.py --model /path/to/Qwen2.5-7B-Instruct-Q4_K_M.gguf
```

Type a scenario on the front page. You watch the team build it, then the Town opens. To use a model
server you already run (Ollama, vLLM, LM Studio, anything OpenAI-compatible):

```bash
export LOCAL_BASE_URL=http://localhost:11434/v1 LOCAL_MODEL_STANDARD=qwen2.5:14b-instruct
python run_local.py
```

No model at all? `python run_local.py --offline` runs a scripted stand-in so you can click through
the whole flow. Its stories are shallow; it is for trying the interface.

**How long it takes.** On a 7B model on a 4 GB laptop GPU (about 7 tokens a second) a build takes
roughly 50 minutes and 100 to 140 model calls, and the town runs about one simulated hour per 25
minutes of real time with four residents. A bigger GPU or a hosted model is much faster. A build ends
when the draft passes review and a trial run, and is merged; the town runs until you pause it.

## What happens

1. **You enter a scenario.** One box on the front page.
2. **The studio builds it.** A lead plans the work; researchers read the web; writers fill in the
   sections (geography, politics, economy, technology, culture, factions, people, tensions); a reviewer
   checks them and sends problems back. Mechanical problems are fixed by rule and listed. You can
   watch every job, answer the team's questions, or let it run on its own.
3. **You merge.** Nothing lands in the world until the merge, which shows what would change.
4. **It becomes a town.** Places become buildings, roads and rooms on a tile map. People take their
   places.
5. **The town lives.** Residents wake on their own clocks, walk real paths, see and hear each other,
   talk, work, quarrel, found groups, make laws, trade and lend, marry and have children. When someone
   walks to the edge of the known ground, the creators draw new land. When someone needs help they walk
   to a shrine and ask **you**; you can grant, whisper, show a sign, refuse, punish or stay silent.
6. **You watch and steer.** Follow anyone, interview them, read the daily paper, see who likes whom
   and why anything happened, scrub back through the day, or run the same world twenty times and see
   what changes.

## Why it is different each time, and still repeatable

Chance comes from the operating system, and every draw is written to a journal. Two live runs differ.
A replay reads the draws and the recorded model replies and makes no decisions of its own, so it is
identical to the run it replays.

## What is in it

| | |
|---|---|
| **Studio** | Task graph, researchers with web search, writers with tool sessions, reviewer, merge gate with diff and partial merge, budgets, audit log. Tuned for small models: exact section shapes, near-miss normalisation, append mode for long lists, automatic repair. |
| **Town** | Residents on their own clocks with optimistic commits; tile map with walls, doors, roads, sight and hearing; walking in legs; map that grows at the edge with checked, budgeted proposals. |
| **Society** | Drives and frustration; three persona edges per person; groups, laws, prices, debts, buildings, sales; petitions and a podium; a daily paper. |
| **Generations** | Marriage, birth with inherited traits, death, inheritance, a skip of years, a cast library. |
| **Many worlds** | Run N times and see in how many runs each outcome held. |
| **Many gods** | God, demigod with a daily budget, observer, and an AI god with a goal of its own. |
| **Cost** | An estimate before a run, budgets per run and per day that slow the town instead of overspending, a model per resident. |
| **Evaluation** | Liveliness, disagreement, coherence, readability, cost and petition quality, with judges gated on calibration. |

## Checks and honest limits

- The last complete test run passed 615 tests. Run `python -m pytest -q` yourself; give it a few
  minutes and an otherwise idle machine.
- Two 48-hour runs of a ten-person town diverged and both replayed to an identical event log.
- On a local Qwen2.5-7B, three full builds (Lucknow, Gandhi's India, a Mars colony) each reached a merge,
  and a three-hour town run had no invariant violations. Small models write thin worlds with few
  people; larger ones do better.
- A three-hour live town run is too short for petitions or new groups to appear. A longer run on a real
  model has not been done. Neither has a run on a hosted model.
- Not built: Postgres for many worlds at once; human labels for calibrating the judges.

Details, numbers and what was tried are in [docs/V7_STATUS.md](docs/V7_STATUS.md),
[docs/V7_PLAN.md](docs/V7_PLAN.md), [docs/V7_EXPERIMENTS.md](docs/V7_EXPERIMENTS.md) and the older
history in [docs/HISTORY.md](docs/HISTORY.md).

## Layout

```
run_local.py        start the model server and the site
tinyworld/
  studio/           the team: foreman, sessions, merge gate, creators, podium desk, job queue
  sim/              clocks (async residents), town, newspaper, lives, cost, replay, watch
  world/            grid, walking, petitions, drives, groups, laws, economy, lives, gods
  genesis/          bible, critic, layout (place graph to tile map)
  gm/ agents/ core/ the Game Master, residents' minds, the event log and reducers
  llm/              clients: local open-weight (OpenAI-compatible), OpenRouter, Gemini, Anthropic
  eval/             benchmarks, multiverse, metrics, experiments
  api/              the website's server and its static app
tests/
```

Hosted models still work (`TINYWORLD_PROVIDER=openrouter`, `gemini` or `anthropic` with their keys),
but the project is built and tested for open-weight models first.

MIT licensed. See [LICENSE](LICENSE).
