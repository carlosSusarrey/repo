"""Adventure cards.

CR 715: Adventure cards have two halves — the creature and the adventure
(an instant or sorcery). When cast as the adventure, the card goes to
exile instead of the graveyard after resolving, and can then be cast
as the creature from exile.

Key rules:
- CR 715.3: While on the stack as an adventure, only the adventure
  characteristics are used.
- CR 715.4: After the adventure resolves, the card is exiled.
- CR 715.5: The card can be cast as the creature from exile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.mana import ManaCost


@dataclass
class AdventureData:
    """The adventure half of a card."""
    name: str
    card_type: CardType  # INSTANT or SORCERY
    cost: ManaCost
    effects: list[dict[str, Any]] = field(default_factory=list)
    rules_text: str = ""


@dataclass
class AdventureState:
    """Tracks adventure state for a card instance."""
    adventure: AdventureData | None = None
    # True when the card is on the stack/resolving as its adventure half
    cast_as_adventure: bool = False
    # True when the card is in exile after the adventure resolved
    on_adventure: bool = False
    # Store the creature card for reference while on adventure
    creature_card: Card | None = None


def setup_adventure(
    card_instance: CardInstance,
    adventure: AdventureData,
) -> None:
    """Set up a card instance with an adventure half."""
    state = AdventureState(adventure=adventure, creature_card=card_instance.card)
    card_instance._adventure_state = state  # type: ignore[attr-defined]


def can_cast_adventure(card_instance: CardInstance) -> bool:
    """Check if the adventure half can be cast.

    The adventure can be cast from hand.
    """
    state = getattr(card_instance, '_adventure_state', None)
    if state is None or state.adventure is None:
        return False
    return card_instance.zone == Zone.HAND and not state.on_adventure


def cast_as_adventure(card_instance: CardInstance) -> AdventureData | None:
    """Begin casting the card as its adventure half.

    CR 715.3: While on the stack as an adventure, the card uses
    the adventure's characteristics.
    """
    state = getattr(card_instance, '_adventure_state', None)
    if state is None or state.adventure is None:
        return None
    if card_instance.zone != Zone.HAND:
        return None

    state.cast_as_adventure = True
    state.creature_card = card_instance.card

    # Temporarily swap to adventure characteristics for casting
    adventure = state.adventure
    adventure_card = Card(
        name=adventure.name,
        card_type=adventure.card_type,
        cost=adventure.cost,
        effects=adventure.effects,
        rules_text=adventure.rules_text,
    )
    card_instance.card = adventure_card
    return adventure


def resolve_adventure(card_instance: CardInstance) -> bool:
    """Resolve the adventure — exile the card instead of putting in graveyard.

    CR 715.4: After adventure resolves, exile the card. It can then
    be cast as the creature from exile.
    """
    state = getattr(card_instance, '_adventure_state', None)
    if state is None or not state.cast_as_adventure:
        return False

    # Restore creature card
    if state.creature_card is not None:
        card_instance.card = state.creature_card

    state.cast_as_adventure = False
    state.on_adventure = True
    card_instance.zone = Zone.EXILE
    return True


def can_cast_from_adventure(card_instance: CardInstance) -> bool:
    """Check if the creature can be cast from exile after the adventure.

    CR 715.5: While in exile after the adventure resolved,
    you may cast the creature.
    """
    state = getattr(card_instance, '_adventure_state', None)
    if state is None:
        return False
    return state.on_adventure and card_instance.zone == Zone.EXILE


def cast_creature_from_adventure(card_instance: CardInstance) -> bool:
    """Cast the creature half from exile after the adventure.

    After this, the card functions as a normal creature spell.
    """
    state = getattr(card_instance, '_adventure_state', None)
    if state is None or not state.on_adventure:
        return False
    if card_instance.zone != Zone.EXILE:
        return False

    # Restore creature card (should already be restored from resolve)
    if state.creature_card is not None:
        card_instance.card = state.creature_card

    state.on_adventure = False
    return True


def is_on_adventure(card_instance: CardInstance) -> bool:
    """Check if a card is in exile on adventure."""
    state = getattr(card_instance, '_adventure_state', None)
    return state is not None and state.on_adventure


def get_adventure(card_instance: CardInstance) -> AdventureData | None:
    """Get the adventure data for a card."""
    state = getattr(card_instance, '_adventure_state', None)
    if state is None:
        return None
    return state.adventure


def has_adventure(card_instance: CardInstance) -> bool:
    """Check if a card has an adventure half."""
    state = getattr(card_instance, '_adventure_state', None)
    return state is not None and state.adventure is not None
