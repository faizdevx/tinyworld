class MemoryRetriever:
    """
    Retrieves memories relevant to a simple text topic.

    Phase 6.11 intentionally uses basic substring matching.
    Smarter retrieval comes later.
    """

    def relevant_memories(self, npc, topic):
        if not topic:
            return []

        normalized_topic = topic.lower()

        return [
            memory
            for memory in npc.memories
            if normalized_topic in memory.event.lower()
        ]