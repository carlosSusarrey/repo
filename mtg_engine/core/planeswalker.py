"""Planeswalker loyalty abilities system.

CR 306: Planeswalkers
CR 306.5: Loyalty abilities are activated abilities with loyalty costs.
CR 306.5d: Only one loyalty ability per planeswalker per turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mtg_engine.core.card import CardInstance
from mtg_engine.core.enums import CardType, Zone


@dataclass
class LoyaltyAbility:
    """A loyalty ability on a planeswalker.

    cost > 0 means "+N" loyalty ability
    cost < 0 means "-N" loyalty ability
    cost == 0 means "0:" loyalty ability
    """
    cost: int
    effects: list[dict[str, Any]] = field(default_factory=list)
    description: str = ""


def get_loyalty(card: CardInstance) -> int:
    """Get current loyalty of a planeswalker."""
    return card.counters.get("loyalty", 0)


def set_loyalty(card: CardInstance, amount: int) -> None:
    """Set loyalty counter value."""
    card.counters["loyalty"] = max(0, amount)


def initialize_loyalty(card: CardInstance) -> None:
    """Set starting loyalty when a planeswalker enters the battlefield.

    CR 306.5b: Planeswalker enters with loyalty counters equal to printed loyalty.
    """
    if card.card.card_type == CardType.PLANESWALKER and card.card.loyalty is not None:
        card.counters["loyalty"] = card.card.loyalty


def can_activate_loyalty(
    card: CardInstance,
    ability_index: int,
    activated_this_turn: set[str],
) -> bool:
    """Check if a loyalty ability can be activated.

    CR 306.5d: Only activate loyalty abilities at sorcery speed,
    and only one per planeswalker per turn.
    """
    if card.zone != Zone.BATTLEFIELD:
        return False
    if card.card.card_type != CardType.PLANESWALKER:
        return False
    if card.instance_id in activated_this_turn:
        return False

    abilities = card.card.activated_abilities
    if ability_index >= len(abilities):
        return False

    ability = abilities[ability_index]
    loyalty_cost = ability.get("loyalty_cost", 0)

    # Can't activate if the cost would reduce loyalty below 0
    current = get_loyalty(card)
    if current + loyalty_cost < 0:
        return False

    return True


def activate_loyalty(
    card: CardInstance,
    ability_index: int,
    activated_this_turn: set[str],
) -> dict[str, Any] | None:
    """Activate a loyalty ability. Returns the effects to resolve, or None if illegal.

    CR 306.5: Paying the loyalty cost is part of the activation cost.
    """
    if not can_activate_loyalty(card, ability_index, activated_this_turn):
        return None

    ability = card.card.activated_abilities[ability_index]
    loyalty_cost = ability.get("loyalty_cost", 0)

    # Pay the loyalty cost
    current = get_loyalty(card)
    set_loyalty(card, current + loyalty_cost)

    # Mark as activated this turn
    activated_this_turn.add(card.instance_id)

    return {
        "source_id": card.instance_id,
        "controller_index": card.controller_index,
        "effects": ability.get("effects", []),
        "card_name": card.name,
    }


def check_planeswalker_uniqueness(
    battlefield: list[CardInstance],
) -> list[tuple[int, str, list[CardInstance]]]:
    """Check for the planeswalker uniqueness rule.

    CR 306.4: If a player controls two or more planeswalkers with the same
    subtypes, they choose one and the rest go to the graveyard.
    Note: This was replaced by the legend rule in 2018. Planeswalkers now
    just use the legend rule (all planeswalkers are legendary).
    """
    # Modern rules: handled by legend rule in SBAs
    return []
