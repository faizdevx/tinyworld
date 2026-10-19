"""Verb groups used by the rule layer and the conflict grouper."""

from tinyworld.core.events import Verb

# Resolved by rules alone when their preconditions hold.
RULE_RESOLVED = frozenset({Verb.MOVE, Verb.SPEAK, Verb.GIVE, Verb.WAIT, Verb.REST, Verb.PETITION, Verb.EXPLORE})

# Verbs whose target has to be within reach of the actor.
NEEDS_REACH = frozenset({Verb.TAKE, Verb.TRADE, Verb.USE, Verb.ATTACK, Verb.GIVE})

# Verbs that compete when two actors aim them at the same target.
CONTESTED = frozenset({Verb.TAKE, Verb.TRADE, Verb.USE, Verb.ATTACK, Verb.MAKE})

DEFAULT_MINUTES = {
    Verb.SPEAK: 2,
    Verb.GIVE: 2,
    Verb.TAKE: 2,
    Verb.WAIT: 15,
    Verb.REST: 60,
    Verb.WORK: 60,
    Verb.PETITION: 5,
}
