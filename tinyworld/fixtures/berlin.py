"""A hand-written bible for the reference premise.

"1941. Germany never invades the USSR. A town near Berlin."

It serves two purposes: a fixture for tests of the genesis pipeline, and the
canned content the offline demo uses when no model is configured. It is one
plausible reading of the premise, not a generated one.
"""

PREMISE_TEXT = "1941. Germany never invades the USSR. A town near Berlin."

PREMISE = {
    "period": "September 1941, third year of the war in the west",
    "start_date": "1941-09-15",
    "place": "Falkenrode, a market town of about 4,000 people 30 km north-west of Berlin",
    "divergence_point": "In spring 1941 the German leadership shelves the invasion of the "
    "Soviet Union. The 1939 non-aggression pact and its trade agreements stay in force.",
    "scope": "One town and its surrounding farms; about a dozen people followed closely.",
    "tone": "Grounded, tense, everyday.",
    "constraints": ["No real historical individuals appear in the town."],
    "questions": [],
}

DIVERGENCE = {
    "summary": "With no eastern front, Germany's war stays in the west and the "
    "Mediterranean. Soviet grain, oil and ore keep arriving by rail under the trade "
    "agreements, paid for with machinery. Rationing continues but is less severe, "
    "and Soviet trade officials become a strange, watched presence in German towns "
    "along the rail lines.",
    "consequences": [
        {
            "order": 1,
            "text": "No mass call-up for an eastern campaign; fewer men leave the town in 1941.",
            "rationale": "The eastern army is not assembled.",
            "confidence": 0.9,
        },
        {
            "order": 1,
            "text": "Soviet grain and oil shipments continue through Brandenburg rail junctions.",
            "rationale": "The 1940 and 1941 commercial agreements remain in effect.",
            "confidence": 0.85,
        },
        {
            "order": 2,
            "text": "German machine works receive export orders for the Soviet Union and must meet delivery dates.",
            "rationale": "The agreements were paid for in machine tools and equipment.",
            "confidence": 0.75,
        },
        {
            "order": 2,
            "text": "Bread rations hold steady, but the party treats the imported grain as a state secret and a point of pride.",
            "rationale": "Dependence on a declared ideological enemy is politically awkward.",
            "confidence": 0.6,
        },
        {
            "order": 3,
            "text": "Local party officials and police are uneasy about Soviet inspectors mixing with German workers.",
            "rationale": "Ideology and trade pull in opposite directions.",
            "confidence": 0.6,
        },
        {
            "order": 3,
            "text": "British night raids on Berlin continue and are the war most townspeople actually feel.",
            "rationale": "The air war in the west is unchanged.",
            "confidence": 0.7,
        },
    ],
}

GEOGRAPHY = {
    "overview": "Falkenrode sits on a branch rail line to Berlin. The market square is "
    "the centre; the machine works and the station lie to the east, farms to the north.",
    "places": [
        {
            "name": "Market Square", "kind": "square", "district": "centre",
            "description": "Cobbled square with a pump and a notice board for decrees.",
            "connects_to": [
                {"to": "Town Hall", "travel_minutes": 2, "audible": True},
                {"to": "Keller Bakery", "travel_minutes": 2, "visible": True, "audible": True},
                {"to": "Golden Stag Inn", "travel_minutes": 3, "audible": True},
                {"to": "St Mary's Church", "travel_minutes": 4},
                {"to": "Schoolhouse", "travel_minutes": 5},
                {"to": "Station Road", "travel_minutes": 6, "visible": True},
            ],
        },
        {
            "name": "Town Hall", "kind": "office", "district": "centre",
            "description": "The mayor's office, the ration card desk and the town records.",
            "connects_to": [],
        },
        {
            "name": "Keller Bakery", "kind": "shop", "district": "centre", "owner": "Anna Keller",
            "description": "A bakery with a shop window on the square.",
            "connects_to": [{"to": "Bakery Store Room", "travel_minutes": 1}],
        },
        {
            "name": "Bakery Store Room", "kind": "storeroom", "district": "centre",
            "enclosed": True, "owner": "Anna Keller",
            "description": "Flour sacks behind a heavy door. Nothing inside is seen or heard from the shop.",
            "connects_to": [],
        },
        {
            "name": "Golden Stag Inn", "kind": "inn", "district": "centre",
            "description": "The town's inn and the place news travels fastest.",
            "connects_to": [],
        },
        {
            "name": "St Mary's Church", "kind": "church", "district": "centre",
            "description": "Lutheran parish church with a small vestry.",
            "connects_to": [],
        },
        {
            "name": "Schoolhouse", "kind": "school", "district": "centre",
            "description": "Two classrooms and the teacher's rooms upstairs.",
            "connects_to": [],
        },
        {
            "name": "Station Road", "kind": "street", "district": "east",
            "description": "The road from the square to the works and the station.",
            "connects_to": [
                {"to": "Railway Station", "travel_minutes": 5, "visible": True, "audible": True},
                {"to": "Brandt Machine Works", "travel_minutes": 4, "audible": True},
                {"to": "Vogel Farm", "travel_minutes": 35},
            ],
        },
        {
            "name": "Railway Station", "kind": "station", "district": "east",
            "description": "A two-platform station with a goods siding where grain wagons are shunted.",
            "connects_to": [{"to": "Goods Shed", "travel_minutes": 2}],
        },
        {
            "name": "Goods Shed", "kind": "warehouse", "district": "east", "enclosed": True,
            "description": "Locked shed for goods in transit, including sealed Soviet grain.",
            "connects_to": [],
        },
        {
            "name": "Brandt Machine Works", "kind": "factory", "district": "east",
            "owner": "Friedrich Brandt",
            "description": "A works of 300 hands turning out lathes, now largely for export east.",
            "connects_to": [],
        },
        {
            "name": "Vogel Farm", "kind": "farm", "district": "north",
            "owner": "Lena Vogel",
            "description": "Rye and potato fields with a barn, an hour's walk from the square.",
            "connects_to": [],
        },
    ],
}

POLITICS = {
    "overview": "The town is run by the mayor under the eye of the party's local group "
    "leader, who answers to the district office in Nauen. The police post has two men. "
    "Real power lies with whoever can report whom.",
    "institutions": [
        {
            "name": "Town Council", "kind": "municipal",
            "description": "Mayor and clerks; issues ration cards and permits.",
            "aims": ["keep order", "meet district quotas"], "leader": "Otto Brandt", "members": 9,
        },
        {
            "name": "District Food Office", "kind": "state office",
            "description": "Sets ration levels and audits flour and grain; based in Nauen.",
            "aims": ["account for every sack"], "members": 20,
        },
        {
            "name": "Police Post", "kind": "police",
            "description": "Two constables who rely on the party's informers.",
            "aims": ["enforce blackout and ration law"], "members": 2,
        },
    ],
    "laws": [
        "Bread, flour, meat and fat are sold only against ration cards.",
        "Blackout is in force from dusk; showing a light is punishable.",
        "Listening to foreign radio broadcasts is a serious crime.",
        "Grain in transit under the trade agreement is state property under seal.",
        "Unauthorised contact with foreign officials must be reported to the party.",
    ],
}

ECONOMY = {
    "overview": "People live on wages, ration cards and what the farms yield. Flour is "
    "audited, coin buys less each month, and favours matter more than marks.",
    "resources": [
        {"name": "bread", "unit": "loaf", "scarcity": "rationed"},
        {"name": "flour", "unit": "sack", "scarcity": "rationed and audited"},
        {"name": "grain", "unit": "sack", "scarcity": "state controlled"},
        {"name": "reichsmark", "unit": "mark", "scarcity": "normal"},
        {"name": "ration card", "unit": "card", "scarcity": "issued monthly"},
        {"name": "potatoes", "unit": "sack", "scarcity": "seasonal"},
        {"name": "machine parts", "unit": "crate", "scarcity": "export priority"},
    ],
    "stocks": [
        {"holder": "Keller Bakery", "resource": "bread", "quantity": 40},
        {"holder": "Bakery Store Room", "resource": "flour", "quantity": 9},
        {"holder": "Goods Shed", "resource": "grain", "quantity": 120},
        {"holder": "Vogel Farm", "resource": "potatoes", "quantity": 30},
        {"holder": "Vogel Farm", "resource": "grain", "quantity": 14},
        {"holder": "Brandt Machine Works", "resource": "machine parts", "quantity": 25},
        {"holder": "Town Hall", "resource": "ration card", "quantity": 200},
    ],
    "scarcities": [
        "Flour allocations to bakers were cut by a tenth in August.",
        "Coal for the winter has not yet been delivered.",
    ],
}

TECHNOLOGY = {
    "overview": "A small German town of 1941: rail, telegraph, telephone at the town "
    "hall and the works, radio sets in many homes, a few motor vehicles short of fuel.",
    "available": [
        "steam railway", "telegraph", "telephone", "radio receiver", "bicycle",
        "motor lorry", "electric light", "typewriter", "machine lathe", "newspaper",
    ],
    "not_yet": [
        "television in homes", "jet aircraft", "atomic bomb", "electronic computer",
        "penicillin in general use", "radar known to the public", "ballpoint pen",
    ],
}

CULTURE = {
    "overview": "A Protestant Brandenburg town where people know each other's business. "
    "Public conformity is expected; private opinion is guarded and traded carefully.",
    "norms": [
        "The official greeting is expected in offices; many avoid it in private.",
        "Complaints about rations are common; complaints about the leadership are dangerous.",
        "Sunday church attendance is still usual among the older townspeople.",
        "Foreigners are watched and seldom spoken to in public.",
    ],
    "daily_life": [
        "Queue for bread at six, before the day shift.",
        "The works whistle marks seven, noon and five.",
        "Evenings at the inn until blackout; the wireless at home after.",
    ],
    "population": [
        {"name": "works hands and families", "count": 1500, "district": "east",
         "description": "Machine works employees; many former union members."},
        {"name": "shopkeepers and clerks", "count": 700, "district": "centre",
         "description": "Tradespeople, town employees, teachers."},
        {"name": "farm households", "count": 1200, "district": "north",
         "description": "Smallholders and hired hands on the surrounding land."},
        {"name": "elderly and pensioners", "count": 600, "district": "centre",
         "description": "The church's core congregation."},
    ],
}

FACTIONS = {
    "factions": [
        {
            "name": "Party Local Group", "kind": "political",
            "description": "The party's cell in the town, with block wardens and informers.",
            "aims": ["enforce loyalty", "watch the Soviet visitors", "report to the district"],
            "leader": "Ernst Kruger", "members": 60, "influence": 80,
        },
        {
            "name": "Works Management", "kind": "economic",
            "description": "The Brandt family and their foremen.",
            "aims": ["deliver the export order on time", "keep the workforce quiet"],
            "leader": "Friedrich Brandt", "members": 12, "influence": 65,
        },
        {
            "name": "Parish Circle", "kind": "religious",
            "description": "The pastor's congregation and its quiet charity network.",
            "aims": ["look after the poor", "avoid open conflict with the party"],
            "leader": "Martin Weiss", "members": 300, "influence": 40,
        },
        {
            "name": "Workers' Circle", "kind": "informal",
            "description": "Former union members at the works who still meet at the inn.",
            "aims": ["better rations for the night shift", "solidarity without being caught"],
            "leader": "Hanna Stein", "members": 25, "influence": 25,
        },
    ]
}

_ERA_UNKNOWN = [
    "anything that happens after September 1941",
    "military plans and decisions made in Berlin",
]

FIGURES = {
    "figures": [
        {
            "name": "Anna Keller", "age": 34, "occupation": "baker",
            "home": "Keller Bakery", "location": "Keller Bakery", "faction": "Parish Circle",
            "summary": "Runs the bakery alone since her husband was called up to France. "
            "Proud, blunt, and keeps two unaudited sacks of flour she should not have.",
            "traits": ["blunt", "hard-working", "suspicious of officials"],
            "values": ["her children", "fair dealing"],
            "goals": ["keep the bakery supplied through winter", "keep the hidden flour hidden"],
            "fears": ["a flour audit", "a telegram about her husband"],
            "secrets": ["hides two sacks of flour from the food office"],
            "speech_style": "short sentences, dry humour",
            "aptitudes": {"baking": 9, "bargaining": 6},
            "education": "village school, bakery apprenticeship",
            "knows": ["baking", "who in town is short of bread", "ration rules"],
            "does_not_know": _ERA_UNKNOWN + ["what the grain in the goods shed is for"],
            "possessions": [
                {"holder": "Anna Keller", "resource": "reichsmark", "quantity": 40},
                {"holder": "Anna Keller", "resource": "ration card", "quantity": 3},
            ],
            "relations": [
                {"to": "Lena Vogel", "kind": "friend and supplier", "value": 60},
                {"to": "Otto Brandt", "kind": "distrust", "value": -25},
                {"to": "Ernst Kruger", "kind": "fear", "value": -50},
                {"to": "Martin Weiss", "kind": "respect", "value": 45},
            ],
        },
        {
            "name": "Otto Brandt", "age": 58, "occupation": "mayor",
            "home": "Town Hall", "location": "Town Hall", "faction": "Party Local Group",
            "summary": "Mayor since 1929, a party member since it became necessary. "
            "Cautious and vain; wants above all not to be blamed.",
            "traits": ["cautious", "vain", "legalistic"],
            "values": ["order", "his own standing"],
            "goals": ["pass the food office audit", "stay on good terms with Kruger"],
            "fears": ["being replaced by a keener party man"],
            "secrets": ["has altered ration card counts to cover a shortfall"],
            "speech_style": "formal, evasive",
            "aptitudes": {"administration": 7, "evasion": 8},
            "education": "gymnasium, law clerk",
            "knows": ["district regulations", "the ration ledgers", "who owes whom"],
            "does_not_know": _ERA_UNKNOWN + ["how the works is really doing"],
            "possessions": [{"holder": "Otto Brandt", "resource": "reichsmark", "quantity": 220}],
            "relations": [
                {"to": "Friedrich Brandt", "kind": "younger brother, rivalry", "value": 10},
                {"to": "Ernst Kruger", "kind": "wary deference", "value": -15},
                {"to": "Anna Keller", "kind": "wary", "value": -10},
            ],
        },
        {
            "name": "Lena Vogel", "age": 22, "occupation": "farmer",
            "home": "Vogel Farm", "location": "Vogel Farm", "faction": "",
            "summary": "Runs the family farm with her father bedridden. Restless and "
            "sharp; sells a little grain off the books to people she trusts.",
            "traits": ["restless", "curious", "impulsive"],
            "values": ["loyalty to friends", "independence"],
            "goals": ["get through the delivery quota", "see something of the world beyond the farm"],
            "fears": ["losing the farm to a quota default"],
            "secrets": ["sells grain to Anna outside the quota"],
            "speech_style": "quick, informal",
            "aptitudes": {"farming": 8, "nerve": 7},
            "education": "village school",
            "knows": ["farm work", "the back lanes", "which officials look the other way"],
            "does_not_know": _ERA_UNKNOWN + ["town hall politics in detail"],
            "possessions": [{"holder": "Lena Vogel", "resource": "reichsmark", "quantity": 15}],
            "relations": [
                {"to": "Anna Keller", "kind": "friend and customer", "value": 70},
                {"to": "Dmitri Volkov", "kind": "curiosity", "value": 20},
                {"to": "Ernst Kruger", "kind": "dislike", "value": -40},
            ],
        },
        {
            "name": "Friedrich Brandt", "age": 51, "occupation": "factory owner",
            "home": "Brandt Machine Works", "location": "Brandt Machine Works",
            "faction": "Works Management",
            "summary": "Owner of the machine works. Practical and driven; the Soviet "
            "export order is the best business he has ever had and he will not lose it.",
            "traits": ["driven", "pragmatic", "impatient"],
            "values": ["the works", "results"],
            "goals": ["ship forty lathes east by November", "keep the party out of his shop floor"],
            "fears": ["the order being cancelled for political reasons", "a strike"],
            "secrets": ["is behind schedule and concealing it from the inspector"],
            "speech_style": "clipped, technical",
            "aptitudes": {"engineering": 8, "management": 7},
            "education": "technical college",
            "knows": ["machine tools", "the export contract", "his workers' grievances"],
            "does_not_know": _ERA_UNKNOWN,
            "possessions": [{"holder": "Friedrich Brandt", "resource": "reichsmark", "quantity": 900}],
            "relations": [
                {"to": "Otto Brandt", "kind": "older brother, contempt", "value": -5},
                {"to": "Dmitri Volkov", "kind": "valued customer", "value": 35},
                {"to": "Hanna Stein", "kind": "respects and fears", "value": 5},
                {"to": "Ernst Kruger", "kind": "resentment", "value": -30},
            ],
        },
        {
            "name": "Martin Weiss", "age": 63, "occupation": "pastor",
            "home": "St Mary's Church", "location": "St Mary's Church", "faction": "Parish Circle",
            "summary": "Pastor for thirty years. Gentle, stubborn, and increasingly "
            "unable to stay silent about what he hears.",
            "traits": ["gentle", "stubborn", "observant"],
            "values": ["conscience", "his congregation"],
            "goals": ["keep the parish poor fed this winter", "decide whether to speak from the pulpit"],
            "fears": ["bringing the party down on his congregation"],
            "secrets": ["keeps a list of families the parish feeds off the ration"],
            "speech_style": "measured, scriptural turns of phrase",
            "aptitudes": {"persuasion": 7, "discretion": 6},
            "education": "university theology",
            "knows": ["everyone's family troubles", "scripture", "who is hungry"],
            "does_not_know": _ERA_UNKNOWN + ["business at the works"],
            "possessions": [{"holder": "Martin Weiss", "resource": "reichsmark", "quantity": 60}],
            "relations": [
                {"to": "Anna Keller", "kind": "parishioner and ally", "value": 55},
                {"to": "Ernst Kruger", "kind": "opposed", "value": -45},
                {"to": "Greta Lang", "kind": "trust", "value": 50},
            ],
        },
        {
            "name": "Greta Lang", "age": 29, "occupation": "schoolteacher",
            "home": "Schoolhouse", "location": "Schoolhouse", "faction": "",
            "summary": "Teaches the upper class. Clever, lonely and careful; listens to "
            "London on the wireless at night and tells no one.",
            "traits": ["clever", "careful", "lonely"],
            "values": ["truth", "her pupils"],
            "goals": ["find one person she can speak honestly with", "protect a pupil whose father was arrested"],
            "fears": ["being denounced by a pupil"],
            "secrets": ["listens to foreign broadcasts"],
            "speech_style": "precise, slightly ironic",
            "aptitudes": {"languages": 8, "teaching": 7},
            "education": "teacher training college; reads Russian and English",
            "knows": ["what London radio says about the war", "some Russian", "her pupils' homes"],
            "does_not_know": ["anything that happens after September 1941", "local black market dealings"],
            "possessions": [{"holder": "Greta Lang", "resource": "reichsmark", "quantity": 35}],
            "relations": [
                {"to": "Martin Weiss", "kind": "confidant", "value": 55},
                {"to": "Ernst Kruger", "kind": "fear", "value": -55},
                {"to": "Dmitri Volkov", "kind": "interest", "value": 15},
            ],
        },
        {
            "name": "Karl Hoffmann", "age": 47, "occupation": "station master",
            "home": "Railway Station", "location": "Railway Station", "faction": "",
            "summary": "Station master and a stickler for paperwork. Knows exactly how "
            "much grain passes through and is tempted by how little anyone else does.",
            "traits": ["meticulous", "resentful", "greedy in small ways"],
            "values": ["his pension", "being owed favours"],
            "goals": ["skim a few sacks without the seals showing", "be promoted to a bigger station"],
            "fears": ["an inspection of the goods shed"],
            "secrets": ["has a duplicate key to the goods shed"],
            "speech_style": "officious, fond of regulations",
            "aptitudes": {"logistics": 8, "forgery": 5},
            "education": "railway service school",
            "knows": ["train timetables", "what is in the goods shed", "who meets which train"],
            "does_not_know": _ERA_UNKNOWN + ["what the party knows about him"],
            "possessions": [{"holder": "Karl Hoffmann", "resource": "reichsmark", "quantity": 80}],
            "relations": [
                {"to": "Dmitri Volkov", "kind": "nervous cooperation", "value": -5},
                {"to": "Ernst Kruger", "kind": "informant", "value": 20},
                {"to": "Lena Vogel", "kind": "acquaintance", "value": 10},
            ],
        },
        {
            "name": "Ernst Kruger", "age": 41, "occupation": "party local group leader",
            "home": "Golden Stag Inn", "location": "Golden Stag Inn", "faction": "Party Local Group",
            "summary": "The party's man in Falkenrode. A failed salesman who found in "
            "the party the importance he always wanted. Ambitious and thin-skinned.",
            "traits": ["ambitious", "thin-skinned", "watchful"],
            "values": ["the party", "being feared"],
            "goals": ["catch someone dealing with the Russian", "be noticed by the district leadership"],
            "fears": ["being thought soft", "the trade policy he must publicly defend"],
            "secrets": ["privately thinks the Soviet trade is a humiliation"],
            "speech_style": "loud, slogans mixed with sly questions",
            "aptitudes": {"intimidation": 7, "cunning": 6},
            "education": "commercial school",
            "knows": ["who informs for him", "party directives", "local grudges"],
            "does_not_know": _ERA_UNKNOWN + ["the real state of the works order"],
            "possessions": [{"holder": "Ernst Kruger", "resource": "reichsmark", "quantity": 120}],
            "relations": [
                {"to": "Otto Brandt", "kind": "contempt", "value": -20},
                {"to": "Dmitri Volkov", "kind": "hostile suspicion", "value": -60},
                {"to": "Karl Hoffmann", "kind": "useful informer", "value": 25},
                {"to": "Martin Weiss", "kind": "enemy", "value": -50},
                {"to": "Hanna Stein", "kind": "suspect", "value": -45},
            ],
        },
        {
            "name": "Dmitri Volkov", "age": 38, "occupation": "Soviet trade inspector",
            "home": "Golden Stag Inn", "location": "Railway Station", "faction": "",
            "summary": "Engineer posted from Moscow to inspect lathes before shipment and "
            "sign off grain deliveries. Courteous, guarded, and reporting to two masters.",
            "traits": ["courteous", "guarded", "exacting"],
            "values": ["doing the job correctly", "getting home alive"],
            "goals": ["certify forty lathes that actually meet tolerance", "learn what Germans really think"],
            "fears": ["a bad report reaching Moscow", "being compromised by a German contact"],
            "secrets": ["sends observations to Soviet intelligence as well as the trade mission"],
            "speech_style": "careful, accented German, dry politeness",
            "aptitudes": {"engineering": 8, "observation": 8},
            "education": "Moscow technical institute",
            "knows": ["machine tolerances", "the trade agreement terms", "how surveillance works"],
            "does_not_know": [
                "anything that happens after September 1941",
                "local German dialect and customs in depth",
                "who in the town informs for the party",
            ],
            "possessions": [{"holder": "Dmitri Volkov", "resource": "reichsmark", "quantity": 300}],
            "relations": [
                {"to": "Friedrich Brandt", "kind": "professional distrust", "value": -10},
                {"to": "Karl Hoffmann", "kind": "necessary contact", "value": 0},
                {"to": "Ernst Kruger", "kind": "wary", "value": -40},
            ],
        },
        {
            "name": "Hanna Stein", "age": 36, "occupation": "lathe operator",
            "home": "Station Road", "location": "Brandt Machine Works", "faction": "Workers' Circle",
            "summary": "The best operator on the floor and the one the others listen to. "
            "Was a union shop steward before 1933 and has not forgotten.",
            "traits": ["steady", "principled", "sardonic"],
            "values": ["solidarity", "plain speaking"],
            "goals": ["win extra rations for the night shift", "keep the circle from being discovered"],
            "fears": ["an informer in the circle", "the camp her brother was sent to"],
            "secrets": ["organises the Workers' Circle meetings"],
            "speech_style": "plain, ironic, Berlin working-class",
            "aptitudes": {"machining": 9, "organising": 8},
            "education": "elementary school, works apprenticeship",
            "knows": ["the true state of the lathe order", "who on the floor can be trusted"],
            "does_not_know": _ERA_UNKNOWN + ["what management tells the inspector"],
            "possessions": [{"holder": "Hanna Stein", "resource": "reichsmark", "quantity": 20}],
            "relations": [
                {"to": "Friedrich Brandt", "kind": "adversary she respects", "value": -5},
                {"to": "Ernst Kruger", "kind": "enemy", "value": -70},
                {"to": "Dmitri Volkov", "kind": "cautious sympathy", "value": 25},
                {"to": "Anna Keller", "kind": "neighbourly", "value": 30},
            ],
        },
    ]
}

TENSIONS = {
    "tensions": [
        {
            "text": "The food office will audit the town's flour and ration ledgers within the month.",
            "parties": ["Anna Keller", "Otto Brandt"],
            "stakes": "Hidden flour and falsified counts could both come to light.",
        },
        {
            "text": "The lathe order for the Soviet Union is behind schedule and the inspector is exacting.",
            "parties": ["Friedrich Brandt", "Dmitri Volkov", "Hanna Stein"],
            "stakes": "The works' future, and whether the floor pays for the delay.",
        },
        {
            "text": "The party leader wants proof of improper contact with the Soviet inspector.",
            "parties": ["Ernst Kruger", "Dmitri Volkov", "Greta Lang", "Lena Vogel"],
            "stakes": "A denunciation would make his career and ruin someone else.",
        },
        {
            "text": "Sealed state grain sits in a shed while the town's bread ration is cut.",
            "parties": ["Karl Hoffmann", "Martin Weiss", "Anna Keller"],
            "stakes": "Theft from the state is a capital matter; hunger is a daily one.",
        },
    ],
    "starting_facts": [
        "It is September 1941 and Germany is at war with Britain.",
        "Germany and the Soviet Union are at peace and trade under a treaty.",
        "Bread and flour are rationed.",
        "A Soviet trade inspector is lodging at the Golden Stag Inn.",
        "The machine works is building lathes for export.",
    ],
}

DIGEST = {
    "overview": "Falkenrode is a town of 4,000 near Berlin in September 1941. Germany "
    "never invaded the Soviet Union: the two states are at peace and trade under treaty, "
    "so Soviet grain passes through the town's station while German lathes go east. The "
    "war is against Britain, felt as rationing, blackout and night raids on Berlin. The "
    "mayor administers; the party's local leader watches and denounces. Flour is "
    "audited, the bread ration was just cut, and sealed state grain sits in the goods "
    "shed. A Soviet inspector lodges at the inn, distrusted by the party and courted by "
    "the factory owner whose export order is late. People conform in public and bargain, "
    "hide and confide in private.",
    "topics": [
        {"name": "law", "text": "Rationing by card; blackout from dusk; foreign radio forbidden; "
         "contact with foreign officials must be reported; grain in transit is sealed state property."},
        {"name": "technology", "text": "Steam rail, telegraph, telephone in offices, household radio, "
         "bicycles, few motor vehicles. No television, computers, jets or atomic weapons."},
        {"name": "money and rations", "text": "Wages are paid in Reichsmarks. A loaf costs under one "
         "mark but needs a ration coupon. Favours and food count for more than cash."},
        {"name": "daily routine", "text": "Bread queue at six, works whistle at seven, noon and five, "
         "the inn until blackout, church on Sunday."},
    ],
}

SECTIONS = {
    "geography": GEOGRAPHY,
    "politics": POLITICS,
    "economy": ECONOMY,
    "technology": TECHNOLOGY,
    "culture": CULTURE,
    "factions": FACTIONS,
    "figures": FIGURES,
    "tensions": TENSIONS,
}


def genesis_handlers() -> dict:
    """FakeLLM handlers that return this bible, whatever the premise says."""
    handlers = {
        "genesis.premise": PREMISE,
        "genesis.divergence": DIVERGENCE,
        "genesis.queries": {
            "queries": [
                "German-Soviet Commercial Agreement 1940",
                "Rationing in Germany during World War II",
                "Brandenburg small town life 1941",
            ]
        },
        "genesis.notes": {"notes": []},
        "critic": {"findings": []},
        "genesis.digest": DIGEST,
    }
    for name, content in SECTIONS.items():
        handlers[f"genesis.section.{name}"] = content
    return handlers
