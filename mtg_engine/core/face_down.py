"""Face-down cards: Morph, Megamorph, Disguise, Manifest.

CR 708: Face-down spells and permanents.
A face-down permanent is a 2/2 creature with no name, no type,
no abilities, no color, and no mana cost.

CR 702.36 (Morph): Cast face-down for {3} as a 2/2 creature.
Turn face-up by paying morph cost (special action, no stack).
CR 702.168 (Disguise): Like morph but grants ward {2} while face-down.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost


# The "blank" card used for face-down creatures
FACE_DOWN_CARD = Card(
    name="",
    card_type=CardType.CREATURE,
    cost=ManaCost(),
    power=2,
    toughness=2,
)


@dataclass
class FaceDownState:
    """Tracks face-down status and costs for a card instance."""
    is_face_down: bool = False
    morph_cost: ManaCost | None = None
    disguise_cost: ManaCost | None = None
    manifest: bool = False  # True if manifested (may not be a creature)
    original_card: Card | None = None  # Store original for reveal


def cast_face_down(
    card_instance: CardInstance,
    morph_cost: ManaCost | None = None,
    disguise_cost: ManaCost | None = None,
) -> bool:
    """Cast a card face-down as a 2/2 creature for {3}.

    CR 702.36a: You may cast a card with morph face-down by paying {3}.
    It enters as a 2/2 face-down creature with no other characteristics.
    """
    face_down = getattr(card_instance, '_face_down_state', None)
    if face_down is None:
        face_down = FaceDownState()

    face_down.is_face_down = True
    face_down.original_card = card_instance.card
    face_down.morph_cost = morph_cost
    face_down.disguise_cost = disguise_cost

    card_instance._face_down_state = face_down  # type: ignore[attr-defined]
    card_instance.card = FACE_DOWN_CARD

    # Disguise grants ward {2} while face-down
    if disguise_cost is not None:
        card_instance.granted_keywords.add(Keyword.WARD)

    return True


def can_turn_face_up(card_instance: CardInstance) -> bool:
    """Check if a face-down card can be turned face-up."""
    face_down = getattr(card_instance, '_face_down_state', None)
    if face_down is None or not face_down.is_face_down:
        return False
    if face_down.original_card is None:
        return False
    return face_down.morph_cost is not None or face_down.disguise_cost is not None


def turn_face_up(card_instance: CardInstance) -> bool:
    """Turn a face-down permanent face-up.

    CR 702.36e: Turning face up is a special action (doesn't use the stack).
    The permanent gets its original characteristics.
    """
    face_down = getattr(card_instance, '_face_down_state', None)
    if face_down is None or not face_down.is_face_down:
        return False
    if face_down.original_card is None:
        return False

    # Restore original card
    card_instance.card = face_down.original_card
    face_down.is_face_down = False

    # Remove disguise ward if it was granted
    if face_down.disguise_cost is not None:
        card_instance.granted_keywords.discard(Keyword.WARD)

    return True


def is_face_down(card_instance: CardInstance) -> bool:
    """Check if a card instance is face-down."""
    face_down = getattr(card_instance, '_face_down_state', None)
    return face_down is not None and face_down.is_face_down


def get_morph_cost(card_instance: CardInstance) -> ManaCost | None:
    """Get the morph/disguise cost for turning face-up."""
    face_down = getattr(card_instance, '_face_down_state', None)
    if face_down is None:
        return None
    return face_down.disguise_cost or face_down.morph_cost


def manifest(card_instance: CardInstance) -> bool:
    """Manifest a card (put face-down as a 2/2 creature).

    CR 701.34: If it's a creature card, it can be turned face-up
    by paying its mana cost.
    """
    face_down = getattr(card_instance, '_face_down_state', None)
    if face_down is None:
        face_down = FaceDownState()

    face_down.is_face_down = True
    face_down.manifest = True
    face_down.original_card = card_instance.card

    # If it's a creature, its mana cost is the turn-face-up cost
    if card_instance.card.is_creature:
        face_down.morph_cost = card_instance.card.cost

    card_instance._face_down_state = face_down  # type: ignore[attr-defined]
    card_instance.card = FACE_DOWN_CARD
    return True
