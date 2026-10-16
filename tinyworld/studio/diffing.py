"""What a draft would change in the live world, in words rather than JSON.

Used by the merge decision: you should see "3 people added, 1 place removed",
not a wall of data. The live world is the bible currently stored for the world;
the draft is what the team wrote. Sections the draft does not touch are not
mentioned.
"""

from dataclasses import dataclass, field

from tinyworld.genesis.bible import ARTIFACTS, Bible

# Sections made of named items, and where the list lives and what to call things.
NAMED = {
    "geography": ("places", "place", "places"),
    "figures": ("figures", "person", "people"),
    "factions": ("factions", "faction", "factions"),
    "politics": ("institutions", "institution", "institutions"),
    "economy": ("resources", "resource", "resources"),
    "tensions": ("tensions", "tension", "tensions"),
}


@dataclass
class SectionDiff:
    section: str
    status: str  # new | changed | unchanged
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    noun: str = ""

    def line(self) -> str:
        if self.status == "unchanged":
            return f"{self.section}: no change"
        bits = []
        if self.added:
            bits.append(f"{len(self.added)} {self.noun} added")
        if self.removed:
            bits.append(f"{len(self.removed)} removed")
        if self.changed:
            bits.append(f"{len(self.changed)} changed")
        label = "new" if self.status == "new" else "changed"
        return f"{self.section}: {label}" + (f" ({', '.join(bits)})" if bits else "")

    def to_dict(self) -> dict:
        return {
            "section": self.section, "status": self.status, "added": self.added,
            "removed": self.removed, "changed": self.changed, "summary": self.line(),
        }


def _items(content: dict | None, key: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for item in (content or {}).get(key, []) or []:
        if isinstance(item, dict):
            name = item.get("name") or item.get("text") or ""
            if name:
                out[str(name)] = item
    return out


def _live_section(live: Bible | None, section: str) -> dict | None:
    if live is None:
        return None
    value = getattr(live, section, None)
    if value is None:
        return None
    dumped = value.model_dump(mode="json")
    if section == "premise" and not dumped.get("start_date"):
        return None
    if section == "geography" and not dumped.get("places"):
        return None
    if section in ("politics", "economy", "technology", "culture", "factions",
                   "figures", "tensions") and not any(dumped.values()):
        return None
    return dumped


def diff(live: Bible | None, draft: dict[str, dict]) -> list[SectionDiff]:
    """One entry per section the draft wrote, in a stable order."""
    order = list(ARTIFACTS)
    out: list[SectionDiff] = []
    for section in sorted(draft, key=lambda s: order.index(s) if s in order else 99):
        new = draft[section]
        old = _live_section(live, section)
        if old is None:
            noun = NAMED.get(section, ("", "", ""))[2]
            key = NAMED.get(section, ("",))[0]
            added = sorted(_items(new, key)) if key else []
            out.append(SectionDiff(section, "new", added=added, noun=noun))
            continue
        if old == new:
            out.append(SectionDiff(section, "unchanged"))
            continue
        if section in NAMED:
            key, _, noun = NAMED[section]
            before, after = _items(old, key), _items(new, key)
            added = sorted(set(after) - set(before))
            removed = sorted(set(before) - set(after))
            changed = sorted(n for n in set(before) & set(after) if before[n] != after[n])
            out.append(SectionDiff(section, "changed", added, removed, changed, noun))
        else:
            keys = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
            out.append(SectionDiff(section, "changed", changed=keys, noun="fields"))
    return out


def summary(diffs: list[SectionDiff]) -> str:
    return "\n".join(d.line() for d in diffs)
