# v7 Phase 0: four experiments

Run with `python -m tinyworld.eval.v7_experiments` on the 10-person Berlin
world, 48 simulated hours, hourly steps. **The model is the scripted stand-in**
(`llm/offline.py`), not a real one. The numbers show that each mechanism works
and what it measures. They do not say how interesting a real model's world is,
and two of the four go/no-go tests need people.

| Experiment | Go if | Measured | Verdict |
|---|---|---|---|
| Petitions | at least half are specific to the person | 49 petitions in 3 runs; **86% specific** | Go for the machinery. Specificity is by construction here (the scripted text is built from the person's goals and fears). The real test is a model writing them: `Town(write_petitions=True)`; not yet run on a model. |
| Chaos dial | people rate 0.5 above 0 | `chaos` 0.0 gave 0 chance events, 0.5 gave 3 to 5, 1.0 gave 3 to 4 per 48 h. Non-routine events per resident-day: 3.2 / 3.4 / 3.4. Outcome spread 0.25 / 0.30 / 0.27 | **Undecided.** The dial works and is recorded. On these proxies it changes little, because the stand-in model's own randomness dominates. The labelling sheet is `docs/v7_chaos_labels.csv`; it needs a person. |
| Newspaper | a reader can name what happened | 6 editions, **0 invented events** (every cited event exists and is from that day); the three stories cover 60% of the day's five weightiest events | **Undecided.** Accuracy is fine. Whether it reads as a story needs a reader. Coverage of 60% says the weights and the three-story limit leave out some big events. |
| Multiverse x5 | runs differ in who did what, not only in phrasing | one world forked 5 times, fresh entropy each. Who-did-what spread **0.43**, phrasing spread 0.72, outcome spread 0.24; 56 end-state facts differ between runs, 77 are the same in all five | **Go.** The runs differ in deeds, not just words. The spread is of a stand-in model that samples; a real model will differ in its own ways. |

## What this found

- **Chaos was too weak** at first: one event per two simulated days for ten
  people. The rate is now per resident (0.3 per resident per day at chaos 1.0).
- **The paper's coverage is only 60%.** The weights favour god acts over deaths
  and finished projects; a fourth story or a better ranking is a later tweak,
  not a design change.
- **Replay holds.** A town run with chance events, petitions, answers and
  editions replays to an identical event log (`tests/test_town.py`). Chance
  draws, petition actions and answers are journaled (`draw`, `town_intents`,
  `drafts`).

## Not done in this phase

- Human labels for chaos and for the newspaper.
- A model writing the petitions (the code exists; no live run yet).
- A real-model multiverse: the five runs used the stand-in.
