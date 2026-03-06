"""Copy effects system (Layer 1).

CR 707: Copy effects create copies of objects.
Copies retain the copiable values of the original:
- Name, mana cost, color, type, subtype, supertype
- Rules text, abilities, power/toughness, loyalty

Copy effects are applied in Layer 1 of the continuous effects system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost


@dataclass
class CopyEffect:
    """Represents a copy effect on a permanent.

    When a permanent copies another, it takes on all copiable values
    of the original (CR 707.2).
    """
    source_id: str        # The permanent doing the copying (e.g., Clone)
    original_id: str      # The permanent being copied
    timestamp: int = 0
    # Optional modifications to the copy ("except..." clauses)
    except_name: str | None = None
    except_types: list[CardType] | None = None
    additional_abilities: list[dict[str, Any]] = field(default_factory=list)
    additional_keywords: set[Keyword] = field(default_factory=set)


def get_copiable_values(card: Card) -> dict[str, Any]:
    """Get the copiable values of a card (CR 707.2).

    Copiable values are: name, mana cost, color indicator,
    card type, subtype, supertype, rules text, abilities,
    power, toughness, and loyalty.
    """
    return {
        "name": card.name,
        "cost": card.cost,
        "card_type": card.card_type,
        "supertypes": list(card.supertypes),
        "subtypes": list(card.subtypes),
        "power": card.power,
        "toughness": card.toughness,
        "loyalty": card.loyalty,
        "rules_text": card.rules_text,
        "keywords": set(card.keywords),
        "effects": list(card.effects),
        "triggered_abilities": list(card.triggered_abilities),
        "activated_abilities": list(card.activated_abilities),
    }


def apply_copy_effect(
    copy_instance: CardInstance,
    original: Card,
    copy_effect: CopyEffect | None = None,
) -> None:
    """Apply copy effect to make copy_instance a copy of original.

    CR 707.3: The copy acquires all copiable values of the original.
    """
    values = get_copiable_values(original)

    # Create a new Card template with copied values
    copied_card = Card(
        name=values["name"],
        card_type=values["card_type"],
        cost=values["cost"],
        supertypes=values["supertypes"],
        subtypes=values["subtypes"],
        power=values["power"],
        toughness=values["toughness"],
        loyalty=values["loyalty"],
        rules_text=values["rules_text"],
        keywords=values["keywords"],
        effects=values["effects"],
        triggered_abilities=values["triggered_abilities"],
        activated_abilities=values["activated_abilities"],
    )

    # Apply "except" modifications
    if copy_effect:
        if copy_effect.except_name is not None:
            copied_card.name = copy_effect.except_name
        if copy_effect.except_types is not None:
            for t in copy_effect.except_types:
                if t not in [copied_card.card_type]:
                    pass  # Add additional types
        for kw in copy_effect.additional_keywords:
            copied_card.keywords.add(kw)

    # Store original card for potential "un-copy" and set the copied card
    copy_instance._original_card = copy_instance.card  # type: ignore[attr-defined]
    copy_instance.card = copied_card


def create_token_copy(
    original: Card,
    owner_index: int = 0,
    controller_index: int = 0,
    modifications: dict[str, Any] | None = None,
) -> CardInstance:
    """Create a token that's a copy of a card (CR 707.8).

    Used by cards like Populate, Embalm, Eternalize.
    """
    values = get_copiable_values(original)

    if modifications:
        values.update(modifications)

    token_card = Card(
        name=values["name"],
        card_type=values["card_type"],
        cost=values.get("cost", ManaCost()),
        supertypes=values.get("supertypes", []),
        subtypes=values.get("subtypes", []),
        power=values.get("power"),
        toughness=values.get("toughness"),
        loyalty=values.get("loyalty"),
        rules_text=values.get("rules_text", ""),
        keywords=values.get("keywords", set()),
        effects=values.get("effects", []),
        triggered_abilities=values.get("triggered_abilities", []),
        activated_abilities=values.get("activated_abilities", []),
    )

    instance = CardInstance(
        card=token_card,
        zone=Zone.BATTLEFIELD,
        owner_index=owner_index,
        controller_index=controller_index,
    )
    instance.is_token = True  # type: ignore[attr-defined]
    return instance


class CopyEffectManager:
    """Manages copy effects for Layer 1 of the continuous effects system."""

    def __init__(self) -> None:
        self._copy_effects: list[CopyEffect] = []
        self._timestamp: int = 0

    def add_copy_effect(self, effect: CopyEffect) -> None:
        """Register a copy effect."""
        self._timestamp += 1
        effect.timestamp = self._timestamp
        self._copy_effects.append(effect)

    def remove_effects_from(self, source_id: str) -> None:
        """Remove copy effects when the copying permanent leaves."""
        self._copy_effects = [
            e for e in self._copy_effects if e.source_id != source_id
        ]

    def get_effects_for(self, source_id: str) -> list[CopyEffect]:
        """Get all copy effects currently on a permanent."""
        return [e for e in self._copy_effects if e.source_id == source_id]

    @property
    def effects(self) -> list[CopyEffect]:
        return list(self._copy_effects)
