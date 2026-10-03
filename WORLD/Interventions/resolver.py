from dataclasses import dataclass
import re
from typing import Any


_SAFE_RULE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class TargetResolution:
    namespace: str
    identifier: str
    value: Any = None
    collection: Any = None
    key: Any = None


class TargetResolver:
    """Resolve only explicit, supported intervention target namespaces."""

    COLLECTION_NAMESPACES = {
        "resource": "resources",
        "npc": "npcs",
        "building": "buildings",
        "entity": "entities",
        "faction": "factions",
    }

    def resolve(self, world, target: str) -> TargetResolution:
        namespace, identifier = self.parse(target)

        if namespace in self.COLLECTION_NAMESPACES:
            collection = getattr(
                world,
                self.COLLECTION_NAMESPACES[namespace],
            )
            if namespace == "resource":
                if identifier not in collection:
                    raise ValueError(f"Unknown resource target: {target}")
                return TargetResolution(
                    namespace,
                    identifier,
                    collection[identifier],
                    collection,
                    identifier,
                )

            for item in collection:
                if item.name == identifier:
                    return TargetResolution(
                        namespace,
                        identifier,
                        item,
                        collection,
                        item,
                    )
            raise ValueError(f"Unknown target: {target}")

        if namespace == "world":
            return self._resolve_world(world, identifier, target)

        if namespace == "environment":
            if identifier not in {
                "drought",
                "random_events_enabled",
                "climate",
            }:
                raise ValueError(f"Unsupported environment target: {target}")
            if identifier == "climate":
                return TargetResolution(
                    namespace,
                    identifier,
                    world.metadata.get("climate"),
                    world.metadata,
                    "climate",
                )
            attribute = (
                "drought_active"
                if identifier == "drought"
                else identifier
            )
            return TargetResolution(
                namespace,
                identifier,
                getattr(world.environment_system, attribute),
                world.environment_system,
                attribute,
            )

        if namespace == "rule":
            self.validate_rule_key(identifier)
            return TargetResolution(
                namespace,
                identifier,
                world.rules.get(identifier),
                world.rules,
                identifier,
            )

        if namespace == "event":
            return TargetResolution(namespace, identifier)

        raise ValueError(f"Unsupported target namespace: {namespace}")

    @staticmethod
    def parse(target: str) -> tuple[str, str]:
        if not isinstance(target, str):
            raise TypeError("target must be a string")
        if target.count(":") != 1:
            raise ValueError(
                "target must use one explicit namespace, such as resource:Food"
            )
        namespace, identifier = target.split(":", 1)
        namespace = namespace.strip().lower()
        identifier = identifier.strip()
        if not namespace or not identifier:
            raise ValueError("target namespace and identifier are required")
        return namespace, identifier

    def _resolve_world(
        self,
        world,
        identifier: str,
        target: str,
    ) -> TargetResolution:
        if identifier.startswith("metadata."):
            key = identifier.removeprefix("metadata.")
            if key not in {"era", "geography", "climate"}:
                raise ValueError(f"Unsupported metadata target: {target}")
            return TargetResolution(
                "world",
                identifier,
                world.metadata.get(key),
                world.metadata,
                key,
            )

        if identifier.startswith("rules."):
            key = identifier.removeprefix("rules.")
            self.validate_rule_key(key)
            return TargetResolution(
                "world",
                identifier,
                world.rules.get(key),
                world.rules,
                key,
            )

        if identifier in {"clock.day", "clock.hour"}:
            key = identifier.removeprefix("clock.")
            return TargetResolution(
                "world",
                identifier,
                getattr(world.clock, key),
                world.clock,
                key,
            )

        raise ValueError(f"Unsupported world target: {target}")

    @staticmethod
    def validate_rule_key(key: str) -> None:
        if not _SAFE_RULE.fullmatch(key) or "__" in key:
            raise ValueError(f"Invalid rule key: {key}")
