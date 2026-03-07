"""Sideboard and "outside the game" mechanics.

CR 400.11: Cards in the sideboard are outside the game.
CR 400.11b: Effects that refer to cards "outside the game"
  can access the sideboard in tournament play.

Relevant cards: Wishes (Burning Wish, etc.), Lessons (Learn mechanic),
Spawnsire of Ulamog, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone


SIDEBOARD_SIZE_CONSTRUCTED = 15
SIDEBOARD_SIZE_COMMANDER = 0  # Commander doesn't use sideboards (normally)


@dataclass
class Sideboard:
    """A player's sideboard (cards outside the game)."""
    cards: list[CardInstance] = field(default_factory=list)
    owner_index: int = 0

    @property
    def size(self) -> int:
        return len(self.cards)

    def find_card(self, instance_id: str) -> CardInstance | None:
        """Find a card in the sideboard by ID."""
        for card in self.cards:
            if card.instance_id == instance_id:
                return card
        return None

    def find_by_name(self, name: str) -> list[CardInstance]:
        """Find cards in the sideboard by name."""
        return [c for c in self.cards if c.card.name == name]

    def find_by_type(self, card_type: CardType) -> list[CardInstance]:
        """Find cards in the sideboard by type."""
        return [c for c in self.cards if c.card.card_type == card_type]

    def find_by_subtype(self, subtype: str) -> list[CardInstance]:
        """Find cards in the sideboard by subtype (e.g., 'Lesson')."""
        return [c for c in self.cards if subtype in c.card.subtypes]

    def remove_card(self, instance_id: str) -> CardInstance | None:
        """Remove a card from the sideboard."""
        card = self.find_card(instance_id)
        if card:
            self.cards.remove(card)
        return card


def wish(
    sideboard: Sideboard,
    card_type: CardType | None = None,
    subtype: str | None = None,
) -> list[CardInstance]:
    """Get wish-able cards from the sideboard.

    CR 400.11b: "A card outside the game" = sideboard in tournament play.
    Different wishes have different type restrictions.
    """
    if card_type is not None:
        return sideboard.find_by_type(card_type)
    if subtype is not None:
        return sideboard.find_by_subtype(subtype)
    return list(sideboard.cards)


def wish_for_card(
    sideboard: Sideboard,
    instance_id: str,
) -> CardInstance | None:
    """Wish for a specific card from the sideboard.

    Removes it from the sideboard and returns it.
    The caller is responsible for putting it into the player's hand.
    """
    return sideboard.remove_card(instance_id)


def learn(sideboard: Sideboard) -> list[CardInstance]:
    """Get Lesson cards from the sideboard (Learn mechanic).

    Learn: You may discard a card. If you do, draw a card.
    OR put a Lesson card from outside the game into your hand.
    """
    return sideboard.find_by_subtype("Lesson")


def swap_sideboard_card(
    sideboard: Sideboard,
    sideboard_card_id: str,
    game_card: CardInstance,
) -> CardInstance | None:
    """Swap a sideboard card with a game card (between-game sideboarding).

    Used between games in a match. The card going out goes to sideboard,
    the card coming in goes to the deck.
    """
    incoming = sideboard.remove_card(sideboard_card_id)
    if incoming is None:
        return None

    # Put the game card into the sideboard
    game_card.zone = Zone.EXILE  # Temporarily; caller moves to library
    sideboard.cards.append(game_card)
    return incoming


def validate_sideboard(
    sideboard: Sideboard,
    max_size: int = SIDEBOARD_SIZE_CONSTRUCTED,
) -> list[str]:
    """Validate sideboard size. Returns list of errors."""
    errors = []
    if sideboard.size > max_size:
        errors.append(
            f"Sideboard has {sideboard.size} cards, maximum is {max_size}"
        )
    return errors


def create_sideboard(
    cards: list[Card],
    owner_index: int = 0,
) -> Sideboard:
    """Create a sideboard from card definitions."""
    instances = []
    for card in cards:
        instance = CardInstance(
            card=card,
            zone=Zone.EXILE,  # Sideboard cards are "outside the game"
            owner_index=owner_index,
            controller_index=owner_index,
        )
        instances.append(instance)
    return Sideboard(cards=instances, owner_index=owner_index)
