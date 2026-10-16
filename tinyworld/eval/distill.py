"""Turn recorded model calls into fine-tuning data for a smaller open model.

The idea (v4): a strong model plays the routine, reactive and conversational
parts of a world well enough that a small open-weight model fine-tuned on its
replies can take over those calls at a fraction of the cost. Every call is
already recorded with its prompt and reply, so the data is free.

What this does and does not do. It selects calls by role and teacher tier,
keeps only replies that are a JSON object, drops duplicates and empty
replies, and writes chat-format JSONL. It does not judge quality. Run the
persona judge or human labels over a sample before training, and re-check the
result with the same judge: a distilled model is only worth shipping if its
believability stays inside a margin of the teacher's.

    python -m tinyworld.eval.distill --db worlds.sqlite --out data.jsonl
"""

import argparse
import json
import sqlite3
from pathlib import Path

DEFAULT_ROLES = ("agent.act", "agent.act.tier1", "agent.scene", "agent.reflect")
TEACHER_TIERS = ("strong", "standard")


def _is_object(text: str) -> bool:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return False
    try:
        value = json.loads(text[start : end + 1])
    except ValueError:
        return False
    return isinstance(value, dict) and bool(value)


def examples(
    db: sqlite3.Connection,
    *,
    roles: tuple[str, ...] = DEFAULT_ROLES,
    tiers: tuple[str, ...] = TEACHER_TIERS,
    limit: int | None = None,
):
    """Yield one chat example per usable recorded call."""
    marks = ",".join("?" for _ in roles)
    tier_marks = ",".join("?" for _ in tiers)
    rows = db.execute(
        f"SELECT role, model, tier, request_json, response_json FROM llm_calls "
        f"WHERE role IN ({marks}) AND tier IN ({tier_marks}) ORDER BY rowid",
        [*roles, *tiers],
    )
    seen: set[int] = set()
    produced = 0
    for role, model, tier, request_json, response_json in rows:
        request = json.loads(request_json)
        reply = json.loads(response_json)
        text = (reply.get("text") or "").strip()
        if reply.get("refused") or not _is_object(text):
            continue
        system = request.get("system", "")
        if request.get("stable_context"):
            system += "\n\n" + request["stable_context"]
        key = hash((role, system, request.get("user", ""), text))
        if key in seen:
            continue
        seen.add(key)
        yield {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": request.get("user", "")},
                {"role": "assistant", "content": text},
            ],
            "meta": {"role": role, "teacher": model, "tier": tier},
        }
        produced += 1
        if limit is not None and produced >= limit:
            return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export recorded calls as fine-tuning data")
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--roles", nargs="*", default=list(DEFAULT_ROLES))
    parser.add_argument("--tiers", nargs="*", default=list(TEACHER_TIERS))
    parser.add_argument("--limit", type=int, default=None)
    options = parser.parse_args(argv)

    db = sqlite3.connect(options.db)
    count = 0
    by_role: dict[str, int] = {}
    with Path(options.out).open("w", encoding="utf-8") as out:
        for example in examples(
            db, roles=tuple(options.roles), tiers=tuple(options.tiers), limit=options.limit
        ):
            out.write(json.dumps(example, ensure_ascii=False) + "\n")
            count += 1
            role = example["meta"]["role"]
            by_role[role] = by_role.get(role, 0) + 1
    print(f"wrote {count} examples to {options.out}")
    for role, n in sorted(by_role.items()):
        print(f"  {role}: {n}")
    print("These replies are not quality-filtered. Judge a sample before training.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
