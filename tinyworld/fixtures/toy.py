"""A hand-written six-place, three-person world for tests and the debug page."""

from datetime import datetime

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.core.session import WorldSession
from tinyworld.core.state import Entity, Fact, PlaceEdge
from tinyworld.core.store import Store

START = datetime(1943, 3, 14, 8, 0)

SQUARE = "place:market_square"
BAKERY = "place:bakery"
BACK_ROOM = "place:bakery_back_room"
TOWN_HALL = "place:town_hall"
TAVERN = "place:tavern"
FARM = "place:keller_farm"

ANNA = "person:anna_keller"
OTTO = "person:otto_brandt"
LENA = "person:lena_vogel"

BREAD = "resource:bread"
GRAIN = "resource:grain"
COIN = "resource:coin"

PERSONAS = {
    ANNA: {
        "summary": "Baker, 34. Proud, blunt, protective of her family.",
        "traits": ["blunt", "hard-working", "suspicious of officials"],
        "values": ["family", "fairness"],
        "goals": ["keep the bakery supplied with grain", "feed her children"],
        "fears": ["requisition of her flour"],
        "speech_style": "short sentences, dry humour",
        "knowledge": {
            "era": "a small German town, spring 1943",
            "education": "village school, apprenticeship",
            "knows": ["baking", "local gossip", "ration rules"],
            "does_not_know": ["anything after March 1943", "foreign affairs beyond rumour"],
        },
    },
    OTTO: {
        "summary": "Mayor, 58. Cautious, vain, wants order above all.",
        "traits": ["cautious", "vain", "legalistic"],
        "values": ["order", "his standing"],
        "goals": ["meet the grain quota", "avoid unrest"],
        "fears": ["being blamed by the district office"],
        "speech_style": "formal, evasive",
        "knowledge": {
            "era": "a small German town, spring 1943",
            "education": "gymnasium, law clerk",
            "knows": ["district regulations", "who owes what"],
            "does_not_know": ["anything after March 1943", "how to bake or farm"],
        },
    },
    LENA: {
        "summary": "Farmhand, 19. Restless, curious, loyal to Anna.",
        "traits": ["restless", "curious", "impulsive"],
        "values": ["loyalty", "freedom"],
        "goals": ["leave for the city someday", "help Anna"],
        "fears": ["being stuck on the farm forever"],
        "speech_style": "quick, informal",
        "knowledge": {
            "era": "a small German town, spring 1943",
            "education": "village school",
            "knows": ["farm work", "the roads around town"],
            "does_not_know": ["anything after March 1943", "town politics in detail"],
        },
    },
}


def _place(entity_id: str, name: str, description: str, **attrs) -> fx.CreateEntity:
    return fx.CreateEntity(
        entity=Entity(
            id=entity_id,
            kind="place",
            name=name,
            attrs={"description": description, **attrs},
        )
    )


def _person(
    entity_id: str, name: str, location: str, occupation: str, age: int, inventory: dict
) -> fx.CreateEntity:
    return fx.CreateEntity(
        entity=Entity(
            id=entity_id,
            kind="person",
            name=name,
            location=location,
            attrs={
                "occupation": occupation,
                "age": age,
                "tier": 0,
                "persona": PERSONAS[entity_id],
            },
            inventory=inventory,
        )
    )


def seed_drafts() -> list[EventDraft]:
    """Events that build the toy world from an empty state."""
    resources = [
        fx.CreateEntity(entity=Entity(id=BREAD, kind="resource", name="bread", attrs={"unit": "loaf"})),
        fx.CreateEntity(entity=Entity(id=GRAIN, kind="resource", name="grain", attrs={"unit": "sack"})),
        fx.CreateEntity(entity=Entity(id=COIN, kind="resource", name="coin", attrs={"unit": "mark"})),
    ]
    places = [
        _place(SQUARE, "Market Square", "The open centre of town.", x=0, y=0),
        _place(BAKERY, "Keller Bakery", "A small bakery facing the square.", x=1, y=0),
        _place(BACK_ROOM, "Bakery Back Room", "A storeroom behind a heavy door.", enclosed=True, x=2, y=0),
        _place(TOWN_HALL, "Town Hall", "The mayor's office and the records.", x=0, y=1),
        _place(TAVERN, "The Golden Stag", "A tavern, loud in the evenings.", x=-1, y=0),
        _place(FARM, "Keller Farm", "Fields and a barn outside town.", x=0, y=-2),
    ]
    edges = [
        fx.SetEdge(a=SQUARE, b=BAKERY, edge=PlaceEdge(travel_minutes=2, visible=True, audible=True)),
        fx.SetEdge(a=BAKERY, b=BACK_ROOM, edge=PlaceEdge(travel_minutes=1)),
        fx.SetEdge(a=SQUARE, b=TOWN_HALL, edge=PlaceEdge(travel_minutes=3, audible=True)),
        fx.SetEdge(a=SQUARE, b=TAVERN, edge=PlaceEdge(travel_minutes=3, audible=True)),
        fx.SetEdge(a=SQUARE, b=FARM, edge=PlaceEdge(travel_minutes=40)),
    ]
    stock = [
        fx.ChangeQuantity(holder=BACK_ROOM, item=GRAIN, delta=6),
        fx.ChangeQuantity(holder=BAKERY, item=BREAD, delta=20),
        fx.ChangeQuantity(holder=FARM, item=GRAIN, delta=30),
    ]
    people = [
        _person(ANNA, "Anna Keller", BAKERY, "baker", 34, {COIN: 12, BREAD: 2}),
        _person(OTTO, "Otto Brandt", TOWN_HALL, "mayor", 58, {COIN: 60}),
        _person(LENA, "Lena Vogel", FARM, "farmhand", 19, {COIN: 3}),
    ]
    relations = [
        fx.SetRelation(source=ANNA, dest=LENA, kind="employer", value=60),
        fx.SetRelation(source=LENA, dest=ANNA, kind="employee", value=70),
        fx.SetRelation(source=ANNA, dest=OTTO, kind="distrust", value=-30),
        fx.SetRelation(source=OTTO, dest=ANNA, kind="wary", value=-10),
    ]
    facts = [
        fx.AssertFact(
            fact=Fact(
                id="fact:grain_rationed",
                text="Grain is rationed by the district office.",
                subject="resource:grain",
                predicate="rationed",
                value=True,
            )
        ),
    ]

    def system(effects, narration):
        return EventDraft(
            kind="system", actor="system", effects=effects,
            narration=narration, visibility="god_only",
        )

    return [
        system(resources, "Resources defined."),
        system(places, "Places created."),
        system(edges, "Places connected."),
        system(stock, "Stock placed."),
        system(people, "People created."),
        system(relations, "Relations set."),
        system(facts, "Starting facts asserted."),
    ]


def build_toy(store: Store | None = None, **session_options) -> WorldSession:
    store = store or Store()
    world_id = store.create_world("Toy town, spring 1943.", START)
    branch_id = store.create_branch(world_id, "main")
    session = WorldSession(store, branch_id, **session_options)
    session.commit(seed_drafts())
    return session
