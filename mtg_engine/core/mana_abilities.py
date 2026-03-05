"""Mana abilities system.

CR 605: Mana abilities are special - they don't use the stack.
CR 605.1a: An activated ability is a mana ability if it could produce mana,
doesn't have a target, and isn't a loyalty ability.
"""

from __future__ import annotations

from typing import Any

from mtg_engine.core.card import CardInstance
from mtg_engine.core.enums import CardType, Color, Zone
from mtg_engine.core.mana import ManaPool


# Standard basic land mana production
BASIC_LAND_MANA: dict[str, Color] = {
    "Plains": Color.WHITE,
    "Island": Color.BLUE,
    "Swamp": Color.BLACK,
    "Mountain": Color.RED,
    "Forest": Color.GREEN,
}


def is_mana_ability(ability: dict[str, Any]) -> bool:
    """Check if an activated ability qualifies as a mana ability.

    CR 605.1a: Produces mana, no target, not a loyalty ability.
    """
    if ability.get("is_loyalty", False):
        return False
    effects = ability.get("effects", [])
    has_mana_effect = any(e.get("type") == "add_mana" for e in effects)
    has_target = ability.get("has_target", False)
    return has_mana_effect and not has_target


def get_basic_land_mana(card: CardInstance) -> Color | None:
    """Get the color of mana a basic land produces."""
    for subtype, color in BASIC_LAND_MANA.items():
        if subtype in card.card.subtypes:
            return color
    return None


def can_tap_for_mana(card: CardInstance) -> bool:
    """Check if a card can be tapped for mana.

    CR 605.3: Mana abilities of lands can be activated even with
    summoning sickness (lands don't have summoning sickness anyway).
    """
    if card.zone != Zone.BATTLEFIELD:
        return False
    if card.tapped:
        return False

    # Basic lands always tap for mana
    if card.card.is_land:
        if get_basic_land_mana(card) is not None:
            return True

    # Non-land mana producers (e.g., mana dorks, artifacts)
    # Check for mana abilities in activated_abilities
    for ability in card.card.activated_abilities:
        if is_mana_ability(ability):
            cost = ability.get("cost", {})
            # If cost requires tap and card is untapped, it can produce
            if cost.get("tap", False) and not card.tapped:
                return True

    return False


def tap_for_mana(card: CardInstance, mana_pool: ManaPool) -> Color | None:
    """Tap a land or mana-producing permanent for mana.

    CR 605.3a: Mana abilities resolve immediately, don't use the stack.
    Returns the color of mana produced, or None if unable.
    """
    if not can_tap_for_mana(card):
        return None

    # Basic land mana
    if card.card.is_land:
        color = get_basic_land_mana(card)
        if color is not None:
            card.tap()
            mana_pool.add(color)
            return color

    # Non-land mana abilities
    for ability in card.card.activated_abilities:
        if is_mana_ability(ability):
            cost = ability.get("cost", {})
            if cost.get("tap", False):
                card.tap()
                for effect in ability.get("effects", []):
                    if effect.get("type") == "add_mana":
                        color_str = effect.get("color", "C")
                        color = _parse_color(color_str)
                        mana_pool.add(color)
                        return color

    return None


def tap_all_lands_for_mana(
    lands: list[CardInstance],
    mana_pool: ManaPool,
) -> list[tuple[str, Color]]:
    """Tap all untapped lands for mana. Returns list of (card_name, color) produced."""
    produced = []
    for land in lands:
        if land.card.is_land and not land.tapped:
            color = tap_for_mana(land, mana_pool)
            if color is not None:
                produced.append((land.name, color))
    return produced


def _parse_color(color_str: str) -> Color:
    """Parse a color string to Color enum."""
    mapping = {
        "W": Color.WHITE,
        "U": Color.BLUE,
        "B": Color.BLACK,
        "R": Color.RED,
        "G": Color.GREEN,
        "C": Color.COLORLESS,
    }
    return mapping.get(color_str, Color.COLORLESS)
