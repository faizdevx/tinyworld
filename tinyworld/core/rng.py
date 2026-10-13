"""Seeded randomness for the rule-based parts of the simulation."""

import hashlib
import random


def seeded(*parts: object) -> random.Random:
    """A generator whose stream depends only on ``parts``.

    Deriving the seed from the branch and sequence number keeps rule-based
    choices reproducible on replay without storing generator state.
    """
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))
