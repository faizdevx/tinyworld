"""A hand-written bible for a second reference premise.

"What if India never had Jio internet in 2016. Lucknow, Uttar Pradesh."

Used by the offline demo when the premise mentions Lucknow, Jio or India. Every
person is invented; no real individual appears. It is one plausible reading of
the premise, not a generated one.
"""

LABEL = "Lucknow, September 2016, without Jio"
KEYWORDS = ("lucknow", "jio", "uttar pradesh", "india")
PREMISE_TEXT = "What if India never had Jio internet in 2016. Lucknow, Uttar Pradesh."

PREMISE = {
    "period": "September 2016, a few days before the date Jio would have launched",
    "start_date": "2016-09-02",
    "place": "The old city of Lucknow, Uttar Pradesh, around Chowk and Aminabad",
    "divergence_point": "Reliance Jio never launches its free prepaid 4G service. Data "
    "stays expensive and metered, handsets stay a luxury, and the price war that "
    "would have followed does not happen.",
    "scope": "A few lanes of the old city and the Gomti Nagar offices across the "
    "river; about a dozen people followed closely.",
    "tone": "Grounded, everyday, economic.",
    "constraints": ["No real individuals appear; all people are invented."],
    "questions": [],
}

DIVERGENCE = {
    "summary": "Mobile data stays priced by the gigabyte and out of reach for most "
    "households. Cash remains how the old city trades, scan-to-pay does not reach "
    "ordinary shops, and the phone is for calls and SMS. The lanes that would have "
    "moved onto video, delivery apps and digital payment stay as they were, and "
    "people who bet on the change are left waiting.",
    "consequences": [
        {
            "order": 1,
            "text": "Prepaid data packs stay expensive; most households use their phones for calls and text.",
            "rationale": "There is no operator forcing a price war.",
            "confidence": 0.9,
        },
        {
            "order": 1,
            "text": "Shops in Chowk and Aminabad take cash only; digital payment is a curiosity.",
            "rationale": "Without cheap data, a payment app is a cost to the shopkeeper.",
            "confidence": 0.85,
        },
        {
            "order": 2,
            "text": "Mobile retailers keep selling basic handsets and recharge coupons rather than smartphones.",
            "rationale": "Cheap data is what makes a smartphone worth owning.",
            "confidence": 0.75,
        },
        {
            "order": 2,
            "text": "Taxi and auto drivers stay on the stand; app-based hailing is a few hundred users.",
            "rationale": "The apps cannot reach enough customers on metered data.",
            "confidence": 0.7,
        },
        {
            "order": 3,
            "text": "Young people who wanted online work move away, or take jobs they did not want.",
            "rationale": "The online economy does not form locally.",
            "confidence": 0.6,
        },
        {
            "order": 3,
            "text": "Established traders keep their grip on credit and supply.",
            "rationale": "The ledger and the handshake are not displaced.",
            "confidence": 0.7,
        },
    ],
}

GEOGRAPHY = {
    "overview": "The old city runs along lanes from Chowk to Aminabad. Across the "
    "river, Gomti Nagar has the offices and the new money. The two are twenty "
    "minutes apart by auto, and not much else connects them.",
    "places": [
        {
            "name": "Chowk Market", "kind": "market", "district": "old city",
            "description": "Crowded lanes of sweets, perfume, cloth and gossip.",
            "connects_to": [
                {"to": "Asha's Chai Stall", "travel_minutes": 2, "visible": True, "audible": True},
                {"to": "Sanchar Mobile Store", "travel_minutes": 4, "audible": True},
                {"to": "Chikankari Workshop", "travel_minutes": 6},
                {"to": "Agarwal Cloth House", "travel_minutes": 5, "visible": True},
                {"to": "Chowk Police Post", "travel_minutes": 3, "audible": True},
                {"to": "Charbagh Taxi Stand", "travel_minutes": 18},
            ],
        },
        {
            "name": "Asha's Chai Stall", "kind": "stall", "district": "old city",
            "owner": "Asha Devi",
            "description": "A kettle, six stools and the best place in Chowk to hear things.",
            "connects_to": [],
        },
        {
            "name": "Sanchar Mobile Store", "kind": "shop", "district": "old city",
            "owner": "Imran Qureshi",
            "description": "Handsets, recharge coupons and a repair bench at the back.",
            "connects_to": [{"to": "Repair Bench", "travel_minutes": 1}],
        },
        {
            "name": "Repair Bench", "kind": "workshop", "district": "old city",
            "enclosed": True, "owner": "Imran Qureshi",
            "description": "A curtained back room where phones are opened and talk stays private.",
            "connects_to": [],
        },
        {
            "name": "Chikankari Workshop", "kind": "workshop", "district": "old city",
            "owner": "Shabana Begum",
            "description": "Embroiderers at floor frames; orders are taken in a notebook.",
            "connects_to": [],
        },
        {
            "name": "Agarwal Cloth House", "kind": "shop", "district": "old city",
            "owner": "Mohan Lal Agarwal",
            "description": "Wholesale cloth on credit, kept in a red cloth ledger.",
            "connects_to": [],
        },
        {
            "name": "Chowk Police Post", "kind": "police", "district": "old city",
            "description": "A booth and a bench, staffed by a sub-inspector and two constables.",
            "connects_to": [],
        },
        {
            "name": "Charbagh Taxi Stand", "kind": "stand", "district": "station",
            "description": "Autos and cabs queue outside the station; the union keeps the order.",
            "connects_to": [
                {"to": "Gomti Nagar Tech Park", "travel_minutes": 25, "visible": False},
                {"to": "Ward Office", "travel_minutes": 15},
            ],
        },
        {
            "name": "Ward Office", "kind": "office", "district": "station",
            "description": "The councillor's room, permits and a long bench of petitioners.",
            "connects_to": [],
        },
        {
            "name": "Gomti Nagar Tech Park", "kind": "office", "district": "gomti nagar",
            "description": "Glass offices and a canteen; the only place with fast data.",
            "connects_to": [{"to": "Riverfront Cafe", "travel_minutes": 8, "visible": True}],
        },
        {
            "name": "Riverfront Cafe", "kind": "cafe", "district": "gomti nagar",
            "description": "Coffee and wifi where the young and the ambitious meet.",
            "connects_to": [],
        },
    ],
}

POLITICS = {
    "overview": "The ward councillor holds the permits and the lanes' goodwill; the "
    "police post answers to the district. The traders' association and the taxi "
    "union have more say in daily life than any office.",
    "institutions": [
        {
            "name": "Ward Council", "kind": "municipal",
            "description": "Issues stall permits, trade licences and water connections.",
            "aims": ["keep the ward quiet", "deliver the councillor's promises before the election"],
            "leader": "Suresh Chandra", "members": 8,
        },
        {
            "name": "Chowk Police Post", "kind": "police",
            "description": "Keeps order, takes complaints and takes tea.",
            "aims": ["avoid trouble at the festival", "keep the traders friendly"],
            "leader": "Ravi Shankar Mishra", "members": 3,
        },
    ],
    "laws": [
        "Stalls need a ward permit renewed each year.",
        "Taxis and autos must be licensed and queue at the stand in turn.",
        "Cash transactions over a fixed amount must be recorded by the shopkeeper.",
    ],
}

ECONOMY = {
    "overview": "Cash and credit run the old city. A recharge coupon and a handful of "
    "rupees buy a day of calls; data is bought in small packs and rationed by the "
    "household. Wholesale runs on a ledger and trust.",
    "resources": [
        {"name": "rupee", "unit": "rupee", "scarcity": "normal"},
        {"name": "data pack", "unit": "pack", "scarcity": "expensive"},
        {"name": "recharge coupon", "unit": "coupon", "scarcity": "normal"},
        {"name": "handset", "unit": "handset", "scarcity": "expensive"},
        {"name": "chikankari cloth", "unit": "piece", "scarcity": "normal"},
        {"name": "tea", "unit": "kettle", "scarcity": "normal"},
        {"name": "ledger credit", "unit": "note", "scarcity": "tight"},
    ],
    "stocks": [
        {"holder": "Sanchar Mobile Store", "resource": "recharge coupon", "quantity": 150},
        {"holder": "Sanchar Mobile Store", "resource": "handset", "quantity": 18},
        {"holder": "Sanchar Mobile Store", "resource": "data pack", "quantity": 40},
        {"holder": "Chikankari Workshop", "resource": "chikankari cloth", "quantity": 30},
        {"holder": "Agarwal Cloth House", "resource": "chikankari cloth", "quantity": 60},
        {"holder": "Asha's Chai Stall", "resource": "tea", "quantity": 12},
    ],
    "scarcities": [
        "Data packs are priced beyond most household budgets.",
        "Credit from wholesalers is tightening before the festival season.",
    ],
}

TECHNOLOGY = {
    "overview": "Feature phones and basic smartphones, costly 3G data, SMS and call "
    "services, cable TV and radio. Offices on the other bank have broadband.",
    "available": [
        "feature phone", "basic smartphone", "3G data pack", "SMS banking",
        "bank account", "cash payment", "broadband in offices", "cable television",
        "auto rickshaw", "recharge coupon",
    ],
    "not_yet": [
        "cheap 4G data plans", "mass scan-to-pay payments", "app-based food delivery at scale",
        "free video calling for households", "app-based taxi hailing for everyone",
    ],
    "dependencies": {
        "cheap 4G data plans": ["3G data pack"],
        "mass scan-to-pay payments": ["basic smartphone", "bank account", "cheap 4G data plans"],
        "app-based food delivery at scale": ["basic smartphone", "cheap 4G data plans"],
        "free video calling for households": ["basic smartphone", "cheap 4G data plans"],
        "app-based taxi hailing for everyone": ["basic smartphone", "cheap 4G data plans"],
    },
}

CULTURE = {
    "overview": "Old Lucknow prizes courtesy, food and long memory. People live close "
    "together and everyone's business is known by the tea hour.",
    "norms": [
        "Elders are addressed with respect and given the first cup.",
        "Debts and favours are remembered across generations.",
        "Public disputes are avoided; they are settled through a go-between.",
        "Festivals, weddings and the lunar calendar set the working year.",
    ],
    "daily_life": [
        "Shops open mid-morning and stay open until late evening.",
        "Tea at the stall at ten and at four.",
        "Prayers and a long afternoon break before the evening trade.",
    ],
    "population": [
        {"name": "shopkeepers and artisans", "count": 9000, "district": "old city",
         "description": "Cloth, embroidery, food and repair trades."},
        {"name": "drivers and station workers", "count": 4000, "district": "station",
         "description": "Autos, cabs and porters."},
        {"name": "office workers", "count": 3000, "district": "gomti nagar",
         "description": "Young professionals in technology and services."},
        {"name": "students", "count": 2500, "district": "old city",
         "description": "College students from nearby neighbourhoods."},
    ],
}

FACTIONS = {
    "factions": [
        {
            "name": "Chowk Traders Association", "kind": "economic",
            "description": "Wholesalers and shopkeepers who set credit terms for the market.",
            "aims": ["keep credit tight and orderly", "oppose anything that cuts margins"],
            "leader": "Mohan Lal Agarwal", "members": 400, "influence": 70,
        },
        {
            "name": "Taxi Union", "kind": "labour",
            "description": "Drivers who keep the queue and negotiate with the council.",
            "aims": ["protect the queue", "fair fares", "keep outsiders out"],
            "leader": "Vikram Yadav", "members": 600, "influence": 55,
        },
        {
            "name": "Mobile Retailers Group", "kind": "economic",
            "description": "Handset and recharge shops that swap tips and cover for each other.",
            "aims": ["hold margins on recharge", "stay ahead of the next handset"],
            "leader": "Imran Qureshi", "members": 35, "influence": 35,
        },
        {
            "name": "Ward Politics", "kind": "political",
            "description": "The councillor's circle of supporters and favour-seekers.",
            "aims": ["deliver before the election", "keep the traders quiet"],
            "leader": "Suresh Chandra", "members": 80, "influence": 60,
        },
    ]
}

_UNKNOWN = ["anything after September 2016", "what other cities are doing online"]

FIGURES = {
    "figures": [
        {
            "name": "Asha Devi", "age": 49, "occupation": "chai stall owner",
            "home": "Asha's Chai Stall", "location": "Asha's Chai Stall", "faction": "",
            "summary": "Has run the stall for twenty years. Hears everything, repeats "
            "what suits her, and is deep in debt to the cloth house.",
            "traits": ["shrewd", "warm", "stubborn"],
            "values": ["her grandchildren", "being owed nothing"],
            "goals": ["clear the loan to Agarwal before the festival", "keep her permit renewed"],
            "fears": ["losing the stall to the councillor's cousin", "illness"],
            "opinion": "a woman with a stall owes no one an apology", "grudge": "Mohan Lal Agarwal, whose interest ate a season's profit", "rival_want": "she wants her permit renewed first, ahead of Ravi Shankar Mishra's friends",
            "secrets": ["pays a small weekly sum to a constable"],
            "speech_style": "teasing, quick, plenty of proverbs",
            "aptitudes": {"people": 9, "money": 5},
            "education": "primary school",
            "knows": ["everyone's business in Chowk", "tea", "who owes whom"],
            "does_not_know": _UNKNOWN + ["how phones work beyond calls"],
            "possessions": [{"holder": "Asha Devi", "resource": "rupee", "quantity": 1800}],
            "relations": [
                {"to": "Mohan Lal Agarwal", "kind": "creditor, wary", "value": -20},
                {"to": "Ravi Shankar Mishra", "kind": "pays him off", "value": -10},
                {"to": "Imran Qureshi", "kind": "friend", "value": 45},
            ],
        },
        {
            "name": "Imran Qureshi", "age": 36, "occupation": "mobile shop owner",
            "home": "Sanchar Mobile Store", "location": "Sanchar Mobile Store",
            "faction": "Mobile Retailers Group",
            "summary": "Sells recharge and handsets. Bet his savings on cheap smartphones "
            "arriving soon; the stock is piling up.",
            "traits": ["anxious", "generous", "technical"],
            "values": ["his reputation", "his daughter's schooling"],
            "goals": ["sell down the handset stock before the festival", "find a supplier who gives credit"],
            "fears": ["losing the shop", "being undercut by the big chains"],
            "opinion": "credit is the only honest way to sell", "grudge": "Mohan Lal Agarwal, who refused him terms", "rival_want": "he wants the festival footfall for handsets, which Asha Devi's stall crowds out",
            "secrets": ["borrowed against the shop to buy stock he cannot sell"],
            "speech_style": "fast, gadget talk, apologetic",
            "aptitudes": {"repair": 9, "selling": 6, "electronics": 8},
            "education": "polytechnic diploma",
            "knows": ["handsets", "recharge margins", "basic smartphone", "electronics"],
            "does_not_know": _UNKNOWN + ["how the big operators set their prices"],
            "possessions": [{"holder": "Imran Qureshi", "resource": "rupee", "quantity": 4200}],
            "relations": [
                {"to": "Asha Devi", "kind": "friend", "value": 45},
                {"to": "Mohan Lal Agarwal", "kind": "owes credit", "value": -15},
                {"to": "Faraz Ansari", "kind": "mentor", "value": 40},
            ],
        },
        {
            "name": "Mohan Lal Agarwal", "age": 61, "occupation": "wholesale cloth merchant",
            "home": "Agarwal Cloth House", "location": "Agarwal Cloth House",
            "faction": "Chowk Traders Association",
            "summary": "Runs credit for half the market from a red ledger. Courteous, "
            "patient and unforgiving about money.",
            "traits": ["patient", "courteous", "calculating"],
            "values": ["his name", "order in the market"],
            "goals": ["keep the association united against new entrants", "collect before the festival"],
            "fears": ["a customer who pays elsewhere", "his son leaving the business"],
            "opinion": "new entrants ruin a market that took generations", "grudge": "Imran Qureshi, who undercuts without asking", "rival_want": "he wants every debt collected by the festival, which squeezes Asha Devi",
            "secrets": ["his ledger is not what the tax office has seen"],
            "speech_style": "formal, slow, never raises his voice",
            "aptitudes": {"credit": 9, "negotiation": 8},
            "education": "intermediate commerce",
            "knows": ["the cloth trade", "credit terms", "the councillor's weak points"],
            "does_not_know": _UNKNOWN + ["anything about apps"],
            "possessions": [{"holder": "Mohan Lal Agarwal", "resource": "rupee", "quantity": 25000}],
            "relations": [
                {"to": "Asha Devi", "kind": "debtor", "value": 10},
                {"to": "Shabana Begum", "kind": "supplier and rival", "value": 5},
                {"to": "Suresh Chandra", "kind": "uses him", "value": 20},
            ],
        },
        {
            "name": "Shabana Begum", "age": 44, "occupation": "chikankari workshop owner",
            "home": "Chikankari Workshop", "location": "Chikankari Workshop", "faction": "",
            "summary": "Runs forty embroiderers and wants to sell directly to buyers "
            "outside Lucknow instead of through the cloth house.",
            "traits": ["ambitious", "exacting", "proud"],
            "values": ["her craftswomen", "quality"],
            "goals": ["find buyers outside Lucknow", "pay her workers on time through the lean season"],
            "fears": ["the merchant cutting her credit", "losing the best embroiderers"],
            "opinion": "chikankari should be sold by the hands that made it", "grudge": "Mohan Lal Agarwal, who pays the middlemen first", "rival_want": "she wants outside buyers, which cuts the cloth house's share",
            "secrets": ["has been sending photos of her work to a buyer in Delhi"],
            "speech_style": "direct, impatient with excuses",
            "aptitudes": {"craft": 9, "management": 7},
            "education": "school to eighth class",
            "knows": ["embroidery", "grading cloth", "basic smartphone"],
            "does_not_know": _UNKNOWN + ["how online buyers pay"],
            "possessions": [{"holder": "Shabana Begum", "resource": "rupee", "quantity": 6500}],
            "relations": [
                {"to": "Mohan Lal Agarwal", "kind": "supplier and rival", "value": -5},
                {"to": "Faraz Ansari", "kind": "employs", "value": 30},
                {"to": "Asha Devi", "kind": "friend", "value": 35},
            ],
        },
        {
            "name": "Faraz Ansari", "age": 23, "occupation": "college graduate, part-time repairer",
            "home": "Chikankari Workshop", "location": "Sanchar Mobile Store",
            "faction": "",
            "summary": "Shabana's nephew. Learned programming in college and cannot "
            "find work that uses it. Keeps trying to build things with slow data.",
            "traits": ["restless", "idealistic", "impatient"],
            "values": ["proving it can be done here", "his aunt's trust"],
            "goals": ["build a way for the workshop to take orders by phone", "get a job in Gomti Nagar"],
            "fears": ["ending up behind a counter", "disappointing his aunt"],
            "opinion": "a degree should buy a better life than this", "grudge": "the college, which graduated him into nothing", "rival_want": "he wants Shabana Begum's orders online, which Mohan Lal Agarwal's agents would lose commission on",
            "secrets": ["failed a final exam and has not told his family"],
            "speech_style": "eager, over-explains, speaks of how it ought to be",
            "aptitudes": {"programming": 8, "electronics": 6, "curiosity": 9},
            "education": "engineering degree, third division",
            "knows": ["programming", "basic smartphone", "electronics"],
            "does_not_know": _UNKNOWN + ["how a business is financed"],
            "possessions": [{"holder": "Faraz Ansari", "resource": "rupee", "quantity": 300}],
            "relations": [
                {"to": "Shabana Begum", "kind": "aunt and employer", "value": 35},
                {"to": "Imran Qureshi", "kind": "mentor", "value": 40},
                {"to": "Karan Verma", "kind": "admires", "value": 25},
            ],
        },
        {
            "name": "Vikram Yadav", "age": 38, "occupation": "taxi driver and union organiser",
            "home": "Charbagh Taxi Stand", "location": "Charbagh Taxi Stand",
            "faction": "Taxi Union",
            "summary": "Drives at night and organises by day. Loud on the stand, quiet "
            "with his wife. Watches the app cabs very carefully.",
            "traits": ["loud", "loyal", "suspicious"],
            "values": ["the union", "fair fares"],
            "goals": ["keep app cabs off the stand", "get the council to fix the queue rules"],
            "fears": ["a rival driver breaking the queue", "losing his licence"],
            "opinion": "app cabs are a tax on drivers", "grudge": "Ravi Shankar Mishra, who fines the stand and not the apps", "rival_want": "he wants app cabs off the stand, which Karan Verma's friends depend on",
            "secrets": ["owes the union's collection fund a sum he cannot repay"],
            "speech_style": "rough, joking, quick to take offence",
            "aptitudes": {"organising": 8, "driving": 9},
            "education": "tenth class",
            "knows": ["roads", "who rides to where", "feature phone"],
            "does_not_know": _UNKNOWN + ["how app dispatch works"],
            "possessions": [{"holder": "Vikram Yadav", "resource": "rupee", "quantity": 900}],
            "relations": [
                {"to": "Suresh Chandra", "kind": "bargains", "value": 0},
                {"to": "Ravi Shankar Mishra", "kind": "uneasy", "value": -10},
                {"to": "Asha Devi", "kind": "regular customer", "value": 25},
            ],
        },
        {
            "name": "Suresh Chandra", "age": 54, "occupation": "ward councillor",
            "home": "Ward Office", "location": "Ward Office", "faction": "Ward Politics",
            "summary": "Elected twice, up for election again. Says yes to everyone and "
            "keeps a list of who owes him.",
            "traits": ["affable", "evasive", "ambitious"],
            "values": ["his seat", "being seen to deliver"],
            "goals": ["be seen opening the new water line", "keep the traders and the union both friendly"],
            "fears": ["a rival from his own party", "an audit of the ward fund"],
            "opinion": "a councillor who is not seen has not done anything", "grudge": "Vikram Yadav, who heckles him", "rival_want": "he wants the water line opened with himself in front, ahead of the union's demand",
            "secrets": ["promised the same permit to two people"],
            "speech_style": "warm, long-winded, promises easily",
            "aptitudes": {"politics": 8, "evasion": 7},
            "education": "graduate, arts",
            "knows": ["permits", "who votes how", "the ward fund"],
            "does_not_know": _UNKNOWN + ["what the young want from the city"],
            "possessions": [{"holder": "Suresh Chandra", "resource": "rupee", "quantity": 12000}],
            "relations": [
                {"to": "Mohan Lal Agarwal", "kind": "funder", "value": 15},
                {"to": "Vikram Yadav", "kind": "bargains", "value": 0},
                {"to": "Asha Devi", "kind": "promised her a permit", "value": 5},
            ],
        },
        {
            "name": "Ravi Shankar Mishra", "age": 47, "occupation": "police sub-inspector",
            "home": "Chowk Police Post", "location": "Chowk Police Post", "faction": "",
            "summary": "Keeps order the way it was kept before him: by knowing everyone. "
            "Overworked and quietly corruptible.",
            "traits": ["tired", "observant", "pragmatic"],
            "values": ["a quiet shift", "his pension"],
            "goals": ["get through the festival without an incident", "collect what he is owed"],
            "fears": ["an inquiry into the post's accounts", "a riot"],
            "opinion": "order is kept by being seen to keep it", "grudge": "Vikram Yadav, who named him in a rally", "rival_want": "he wants his tea money kept quiet, which Asha Devi's loud complaints threaten",
            "secrets": ["accepts tea money from several stalls"],
            "speech_style": "laconic, bureaucratic",
            "aptitudes": {"people": 7, "authority": 6},
            "education": "graduate, police training",
            "knows": ["the lanes", "who is feuding", "legal procedure"],
            "does_not_know": _UNKNOWN + ["how digital evidence works"],
            "possessions": [{"holder": "Ravi Shankar Mishra", "resource": "rupee", "quantity": 3000}],
            "relations": [
                {"to": "Asha Devi", "kind": "takes her money", "value": 10},
                {"to": "Vikram Yadav", "kind": "uneasy", "value": -10},
                {"to": "Suresh Chandra", "kind": "defers", "value": 5},
            ],
        },
        {
            "name": "Karan Verma", "age": 27, "occupation": "software engineer",
            "home": "Gomti Nagar Tech Park", "location": "Riverfront Cafe", "faction": "",
            "summary": "Works for a firm whose product needs fast data. Tired of "
            "explaining why his own family cannot use it.",
            "traits": ["wry", "capable", "restless"],
            "values": ["craft", "his independence"],
            "goals": ["leave for a city with better connectivity", "help someone in Chowk build something real"],
            "fears": ["staying in a dead-end job", "his parents' expectations"],
            "opinion": "a city that cannot hold a signal is not a city", "grudge": "his old manager, who passed him over", "rival_want": "he wants to leave, which leaves Faraz Ansari's phone-order plan without help",
            "secrets": ["has an offer from Bangalore and has not told his employer"],
            "speech_style": "dry, English words mixed into Hindi",
            "aptitudes": {"programming": 9, "teaching": 5},
            "education": "engineering degree, private college",
            "knows": ["programming", "broadband in offices", "basic smartphone"],
            "does_not_know": _UNKNOWN + ["how the old city trades"],
            "possessions": [{"holder": "Karan Verma", "resource": "rupee", "quantity": 7000}],
            "relations": [
                {"to": "Faraz Ansari", "kind": "friendly mentor", "value": 25},
                {"to": "Imran Qureshi", "kind": "buys phones from", "value": 10},
            ],
        },
    ],
}

TENSIONS = {
    "tensions": [
        {
            "text": "Asha's loan to the cloth house falls due before the festival, and her permit is up for renewal.",
            "parties": ["Asha Devi", "Mohan Lal Agarwal", "Suresh Chandra"],
            "stakes": "Her stall, and the family it feeds.",
        },
        {
            "text": "Imran holds stock bought on credit for a smartphone boom that has not come.",
            "parties": ["Imran Qureshi", "Mohan Lal Agarwal"],
            "stakes": "His shop, and his daughter's schooling.",
        },
        {
            "text": "Shabana wants to bypass the cloth house and sell directly, and Faraz is trying to build the way.",
            "parties": ["Shabana Begum", "Faraz Ansari", "Mohan Lal Agarwal"],
            "stakes": "Her workshop's independence, and the merchant's grip on credit.",
        },
        {
            "text": "App cabs are trying to enter, and the taxi queue is breaking under the festival rush.",
            "parties": ["Vikram Yadav", "Suresh Chandra", "Ravi Shankar Mishra"],
            "stakes": "The union's authority and the councillor's election.",
        },
    ],
    "starting_facts": [
        "It is September 2016 in Lucknow.",
        "Mobile data is sold in small, expensive packs.",
        "Most shops in the old city take cash only.",
        "The festival season begins in a few weeks.",
        "The ward councillor faces an election next year.",
    ],
}

DIGEST = {
    "overview": "Lucknow's old city in September 2016. Reliance Jio never launched its "
    "free 4G, so data stays expensive, handsets stay a luxury and cash and credit run "
    "the market. Shopkeepers in Chowk live on a red ledger and the festival season; "
    "taxi drivers hold the queue against app cabs that cannot reach enough users. "
    "Across the river the offices in Gomti Nagar have fast data and nobody to share it "
    "with. A tea-stall owner owes the cloth merchant, a mobile shop owner is stuck "
    "with stock bought for a boom that never came, and a young graduate keeps trying "
    "to build something that the network will not carry.",
    "topics": [
        {"name": "money and credit", "text": "Rupees and ledger credit. The cloth house "
         "lends to half the market. Digital payment is rare; shops record cash."},
        {"name": "technology", "text": "Feature phones and basic smartphones, 3G data in "
         "small packs, SMS banking. No cheap 4G, no mass scan-to-pay, no app delivery."},
        {"name": "politics", "text": "The ward councillor issues permits and faces an "
         "election. The police post runs on tea money and acquaintance. The taxi union "
         "keeps the queue."},
        {"name": "daily routine", "text": "Shops open mid-morning, tea at ten and four, "
         "an afternoon break, trade until late evening."},
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
                "Reliance Jio launch September 2016",
                "Mobile data prices India 2016",
                "Chowk Lucknow trade and markets",
            ]
        },
        "genesis.notes": {"notes": []},
        "critic": {"findings": []},
        "genesis.digest": DIGEST,
    }
    for name, content in SECTIONS.items():
        handlers[f"genesis.section.{name}"] = content
    return handlers
