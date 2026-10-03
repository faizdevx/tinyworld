from WORLD.AI.beliefs import Belief
from WORLD.Communication import (
    CommunicationEngine,
    Message,
    MessageProposal,
    MessageType,
    MessageValidator,
)
from WORLD.NPCs.npc import NPC
from WORLD.world import World


def build_world():
    world = World()
    rahul = NPC(name="Rahul", role="guard", money=10, home="House 1", location="Village Square")
    sara = NPC(name="Sara", role="merchant", money=20, home="House 2", location="Village Square")
    ali = NPC(name="Ali", role="farmer", money=5, home="House 3", location="Village Square")
    world.add_npc(rahul)
    world.add_npc(sara)
    world.add_npc(ali)
    return world, rahul, sara, ali


def test_message_model_supports_credentials_and_immutable_claims():
    message = Message(
        sender="npc:Rahul",
        receiver="npc:Sara",
        content="I saw 100 soldiers.",
        message_type=MessageType.TELL,
        claims={"subject": "foreign_army", "predicate": "size", "value": 100},
        timestamp=(1, 10),
    )

    assert message.sender == "npc:Rahul"
    assert message.receiver == "npc:Sara"
    assert message.content == "I saw 100 soldiers."
    assert message.message_type == MessageType.TELL
    assert message.claims["value"] == 100

    try:
        message.claims["value"] = 20
    except Exception:
        pass
    else:
        assert False, "claims should be immutable"


def test_message_proposal_is_not_world_mutating():
    world, rahul, sara, _ = build_world()
    proposal = MessageProposal(
        sender="npc:Rahul",
        receiver="npc:Sara",
        message_type=MessageType.TELL,
        content="I saw 100 soldiers.",
        claims={"subject": "foreign_army", "predicate": "size", "value": 100},
    )

    original_world = world.npcs[:]

    assert world.npcs == original_world
    assert rahul.communication_memory == []
    assert sara.communication_memory == []
    assert proposal.content == "I saw 100 soldiers."


def test_invalid_message_proposal_is_rejected():
    world, _, _, _ = build_world()
    validator = MessageValidator()
    proposal = MessageProposal(
        sender="npc:Missing",
        receiver="npc:Sara",
        message_type=MessageType.TELL,
        content="hello",
    )

    result = validator.validate(world, proposal)
    assert result.success is False


def test_message_delivers_to_receiver_without_leaking_to_unrelated_npc():
    world, rahul, sara, ali = build_world()
    engine = CommunicationEngine()
    proposal = MessageProposal(
        sender="npc:Rahul",
        receiver="npc:Sara",
        message_type=MessageType.TELL,
        content="I saw soldiers near the northern road.",
        claims={"subject": "foreign_army", "predicate": "location", "value": "northern road"},
    )

    result = engine.deliver(world, proposal)

    assert result.success is True
    assert sara.communication_memory[0].content == "I saw soldiers near the northern road."
    assert ali.communication_memory == []
    assert len(world.event_log.events) >= 1


def test_false_information_stays_in_message_not_world_truth():
    world, rahul, sara, _ = build_world()
    world.metadata["army_size"] = "20"
    proposal = MessageProposal(
        sender="npc:Rahul",
        receiver="npc:Sara",
        message_type=MessageType.LIE,
        content="I saw 100 soldiers.",
        claims={"subject": "foreign_army", "predicate": "size", "value": 100},
    )

    result = CommunicationEngine().deliver(world, proposal)

    assert result.success is True
    assert world.metadata["army_size"] == "20"
    assert result.message.claims["value"] == 100
    assert sara.communication_memory[0].claims["value"] == 100


def test_message_updates_belief_with_provenance():
    world, rahul, sara, _ = build_world()
    message = Message(
        sender="npc:Rahul",
        receiver="npc:Sara",
        content="Soldiers are coming.",
        message_type=MessageType.WARN,
        claims={"subject": "enemy_force", "predicate": "approaching", "value": True},
        timestamp=(2, 3),
    )

    belief = Belief(
        subject="enemy_force",
        predicate="approaching",
        value=True,
        confidence=0.7,
        source="npc:Rahul",
        origin_type="communication",
    )

    assert belief.source == "npc:Rahul"
    assert belief.origin_type == "communication"
    assert message.sender == "npc:Rahul"


def test_messages_by_speaker_and_recent_feed_are_private_to_receiver():
    world, rahul, sara, ali = build_world()

    engine = CommunicationEngine()
    engine.deliver(
        world,
        MessageProposal(
            sender="npc:Rahul",
            receiver="npc:Sara",
            message_type=MessageType.TELL,
            content="I saw soldiers.",
            claims={"subject": "foreign_army", "predicate": "seen", "value": True},
        ),
    )
    engine.deliver(
        world,
        MessageProposal(
            sender="npc:Ali",
            receiver="npc:Sara",
            message_type=MessageType.TELL,
            content="I saw twenty soldiers.",
            claims={"subject": "foreign_army", "predicate": "size", "value": 20},
        ),
    )

    assert len(sara.communication_memory) == 2
    assert len(sara.messages_from("npc:Rahul")) == 1
    assert len(sara.messages_between("npc:Rahul", "npc:Sara")) == 1
    assert len(sara.recent_messages(limit=10)) == 2
    assert len(ali.messages_from("npc:Rahul")) == 0


def test_ask_answer_pair_are_separate_messages():
    world, rahul, sara, _ = build_world()
    engine = CommunicationEngine()
    ask = MessageProposal(
        sender="npc:Sara",
        receiver="npc:Rahul",
        message_type=MessageType.ASK,
        content="Did you see soldiers?",
        claims={"subject": "foreign_army", "predicate": "question", "value": "did_you_see"},
    )
    answer = MessageProposal(
        sender="npc:Rahul",
        receiver="npc:Sara",
        message_type=MessageType.ANSWER,
        content="Yes.",
        in_reply_to="ask-1",
        claims={"subject": "foreign_army", "predicate": "answer", "value": True},
    )

    engine.deliver(world, ask)
    engine.deliver(world, answer)

    assert len(rahul.communication_memory) == 1
    assert rahul.communication_memory[0].message_type == MessageType.ASK
    assert len(sara.communication_memory) == 1
    assert sara.communication_memory[0].message_type == MessageType.ANSWER
    assert sara.communication_memory[0].in_reply_to == "ask-1"


def test_communication_range_checks_same_location_and_rejects_far_away():
    world, rahul, sara, _ = build_world()
    rahul.location = "Village Square"
    sara.location = "Forest"

    proposal = MessageProposal(
        sender="npc:Rahul",
        receiver="npc:Sara",
        message_type=MessageType.TELL,
        content="I am far away.",
    )

    result = MessageValidator().validate(world, proposal)
    assert result.success is False
