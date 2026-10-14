# Concepts carried from v1 into v2

`WORLD/` was the v1 package. It was removed once v2 had these ideas; it remains in the git history.

| v1 concept | v1 location | v2 home | What changes |
|---|---|---|---|
| Proposal → validate → resolve → consequence | `Events/engine.py` | `gm/rules.py`, `gm/adjudicator.py`, `core/reducers.py` | Vocabulary becomes the closed effect set in `core/effects.py`. |
| `namespace:name` targets | `Interventions/resolver.py` | `core/ids.py` | Same form, used for every entity id. |
| `Observation` (type, distance, confidence, attention limit) | `AI/observation.py` | `gm/perception.py` | Distances come from the place graph, not a fixed table. |
| `Message` with typed `claims` | `Communication/communication.py` | `Utter` effect | A message is an effect inside an event, so it is replayable. |
| `Belief` (subject, predicate, value, confidence, source, origin) | `AI/beliefs.py` | `agents/beliefs.py` | Adds evidence and time. |
| Truth versus belief comparison | `Observatory.compare_beliefs` | `agents/beliefs.py::compare_beliefs` | Truth index is derived from `WorldState`. |
| Weighted memory retrieval | `AI/memory_retrieval.py` | `agents/retrieval.py` | Lexical match becomes embedding similarity. Weights start from v1's. |
| God operations and visibility | `Interventions/models.py` | `god/` | Every operation compiles to events. |
| Seeded RNG for rule-based parts | `Simulation/rng.py` | `core/rng.py` | Unchanged in spirit. |

Not carried: the food/shop/farm systems, the utility-scoring brain, the `ActionType` enum,
the day/hour clock, the hand-written checkpoint format.
