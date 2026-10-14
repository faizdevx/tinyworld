"""Prepared worlds for the offline demo, and which one fits a premise."""

from types import ModuleType

from tinyworld.fixtures import berlin, lucknow

BERLIN_KEYWORDS = ("berlin", "german", "nazi", "ussr", "soviet", "1941", "reich", "wehrmacht")

# (key, module, keywords). Order is the order they are tried in.
WORLDS: list[tuple[str, ModuleType, tuple[str, ...]]] = [
    ("lucknow", lucknow, lucknow.KEYWORDS),
    ("berlin", berlin, BERLIN_KEYWORDS),
]


def label_of(module: ModuleType) -> str:
    return getattr(module, "LABEL", "Falkenrode near Berlin, September 1941")


def pick(premise: str) -> tuple[str, ModuleType, bool]:
    """(key, module, matched). With no match the Berlin world is returned."""
    text = premise.lower()
    for key, module, words in WORLDS:
        if any(word in text for word in words):
            return key, module, True
    return "berlin", berlin, False


def by_key(key: str) -> ModuleType | None:
    for name, module, _ in WORLDS:
        if name == key:
            return module
    return None
