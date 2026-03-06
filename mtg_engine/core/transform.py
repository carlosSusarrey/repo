"""Double-faced cards (DFCs) and transform mechanic.

CR 712: Double-faced cards have two faces. A player can see both
faces at any time. The front face is the default.

CR 701.28: Transform — turn a transforming double-faced card
to its other face. Only DFCs can transform.

Modal double-faced cards (MDFCs) are different — the player
chooses which face to play when casting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType


@dataclass
class DoubleFacedCard:
    """A card with two faces (front and back).

    Used for transforming DFCs (Werewolves, Ixalan flip cards, etc.)
    and modal DFCs (Pathway lands, Zendikar Rising, etc.).
    """
    front_face: Card
    back_face: Card
    is_modal: bool = False  # True for MDFCs, False for transforming DFCs

    @property
    def name(self) -> str:
        """DFCs use only the front face name in all zones except battlefield/stack."""
        return self.front_face.name


@dataclass
class TransformState:
    """Tracks transform status for a card instance."""
    dfc: DoubleFacedCard | None = None
    is_transformed: bool = False
    is_back_face: bool = False  # For MDFCs cast as back face

    @property
    def current_face(self) -> Card | None:
        """Get the currently active face."""
        if self.dfc is None:
            return None
        if self.is_transformed or self.is_back_face:
            return self.dfc.back_face
        return self.dfc.front_face


def setup_dfc(card_instance: CardInstance, dfc: DoubleFacedCard) -> None:
    """Set up a card instance as a double-faced card."""
    state = TransformState(dfc=dfc)
    card_instance._transform_state = state  # type: ignore[attr-defined]
    card_instance.card = dfc.front_face


def can_transform(card_instance: CardInstance) -> bool:
    """Check if a card instance can transform.

    Only transforming DFCs (not MDFCs) can transform.
    """
    state = getattr(card_instance, '_transform_state', None)
    if state is None or state.dfc is None:
        return False
    return not state.dfc.is_modal


def transform(card_instance: CardInstance) -> bool:
    """Transform a double-faced card to its other face.

    CR 701.28a: Only transforming DFCs can transform.
    """
    state = getattr(card_instance, '_transform_state', None)
    if state is None or state.dfc is None:
        return False
    if state.dfc.is_modal:
        return False

    state.is_transformed = not state.is_transformed
    card_instance.card = state.current_face or card_instance.card
    return True


def is_transformed(card_instance: CardInstance) -> bool:
    """Check if a DFC is currently showing its back face via transform."""
    state = getattr(card_instance, '_transform_state', None)
    return state is not None and state.is_transformed


def get_dfc(card_instance: CardInstance) -> DoubleFacedCard | None:
    """Get the DFC data if this is a double-faced card."""
    state = getattr(card_instance, '_transform_state', None)
    if state is None:
        return None
    return state.dfc


def cast_as_back_face(card_instance: CardInstance) -> bool:
    """Cast a modal DFC as its back face.

    CR 712.8: When casting an MDFC, you choose which face to cast.
    """
    state = getattr(card_instance, '_transform_state', None)
    if state is None or state.dfc is None:
        return False
    if not state.dfc.is_modal:
        return False

    state.is_back_face = True
    card_instance.card = state.dfc.back_face
    return True


def get_front_face(card_instance: CardInstance) -> Card | None:
    """Get the front face of a DFC."""
    state = getattr(card_instance, '_transform_state', None)
    if state is None or state.dfc is None:
        return None
    return state.dfc.front_face


def get_back_face(card_instance: CardInstance) -> Card | None:
    """Get the back face of a DFC."""
    state = getattr(card_instance, '_transform_state', None)
    if state is None or state.dfc is None:
        return None
    return state.dfc.back_face
