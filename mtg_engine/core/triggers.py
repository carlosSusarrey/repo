"""Triggered abilities framework.

Handles "when", "whenever", and "at" triggers for game events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class TriggerEvent(Enum):
    """Events that can trigger abilities."""

    # Zone change triggers
    ENTERS_BATTLEFIELD = auto()
    LEAVES_BATTLEFIELD = auto()
    DIES = auto()  # creature goes from battlefield to graveyard
    CAST = auto()  # a spell is cast

    # Combat triggers
    ATTACKS = auto()
    BLOCKS = auto()
    BECOMES_BLOCKED = auto()
    DEALS_COMBAT_DAMAGE = auto()
    DEALS_COMBAT_DAMAGE_TO_PLAYER = auto()

    # Phase/step triggers
    BEGIN_UPKEEP = auto()
    BEGIN_COMBAT = auto()
    END_STEP = auto()

    # Other triggers
    GAIN_LIFE = auto()
    LOSE_LIFE = auto()
    DRAW_CARD = auto()
    LAND_ENTERS = auto()  # landfall


# Relation keywords determine the relationship between the trigger source
# and the event source (self, another, any, you).
_RELATION_KEYWORDS = {"self", "another", "any", "you"}

# Card type keywords filter by the event source's card type.
# These correspond to permanent types in Magic.
_CARD_TYPE_KEYWORDS = {
    "creature", "artifact", "enchantment", "planeswalker",
    "land", "battle", "kindred",
}

# Token status keywords filter by whether the event source is a token.
_TOKEN_KEYWORDS = {"token", "nontoken"}

# All recognized filter keywords.
FILTER_KEYWORDS = _RELATION_KEYWORDS | _CARD_TYPE_KEYWORDS | _TOKEN_KEYWORDS


def parse_source_filter(source: str | dict[str, Any]) -> dict[str, Any]:
    """Normalize a source filter to a structured dict.

    Accepts either:
      - A legacy string like "self", "creature", "another"
      - A structured dict with optional keys: relation, card_type, token

    Returns a dict with optional keys:
      - "relation": "self" | "another" | "any" | "you"
      - "card_type": "creature" | "artifact" | "enchantment" | etc.
      - "token": True (only tokens) | False (only non-tokens)
    """
    if isinstance(source, dict):
        return source

    # Legacy string — could be a single keyword
    source = source.strip()
    if source in _RELATION_KEYWORDS:
        return {"relation": source}
    if source in _CARD_TYPE_KEYWORDS:
        return {"card_type": source}
    if source == "token":
        return {"token": True}
    if source == "nontoken":
        return {"token": False}
    if source == "permanent":
        return {"card_type": "permanent"}
    # Unknown filter — treat as "any"
    return {}


@dataclass
class TriggerCondition:
    """Defines when a triggered ability fires."""

    event: TriggerEvent
    source_filter: dict[str, Any] = field(default_factory=lambda: {"relation": "self"})
    # Additional conditions
    condition: dict[str, Any] | None = None


@dataclass
class TriggeredAbility:
    """A triggered ability on a card."""

    trigger: TriggerCondition
    effects: list[dict[str, Any]] = field(default_factory=list)
    # Which card this ability belongs to
    source_card_id: str = ""
    controller_index: int = 0


@dataclass
class PendingTrigger:
    """A triggered ability that has been triggered and is waiting to go on the stack."""

    ability: TriggeredAbility
    source_card_id: str
    controller_index: int
    event_data: dict[str, Any] = field(default_factory=dict)


class TriggerManager:
    """Manages trigger registration and event processing."""

    def __init__(self) -> None:
        self._pending: list[PendingTrigger] = []

    @property
    def has_pending(self) -> bool:
        return len(self._pending) > 0

    @property
    def pending(self) -> list[PendingTrigger]:
        return list(self._pending)

    def clear_pending(self) -> None:
        self._pending.clear()

    def pop_pending(self) -> PendingTrigger | None:
        if self._pending:
            return self._pending.pop(0)
        return None

    def check_triggers(
        self,
        event: TriggerEvent,
        event_data: dict[str, Any],
        battlefield_cards: list,
        graveyard_cards: list | None = None,
    ) -> list[PendingTrigger]:
        """Check all cards for triggers matching this event.

        Args:
            event: The event that occurred
            event_data: Context about the event (e.g., which card, which player)
            battlefield_cards: All CardInstances on the battlefield
            graveyard_cards: Cards in graveyard (for death triggers)

        Returns:
            List of triggered abilities that fired
        """
        triggered = []

        # Check battlefield cards
        cards_to_check = list(battlefield_cards)

        # For death triggers, also check the card that just died
        # For LTB triggers, also check graveyard cards (the card that just left)
        if event in (TriggerEvent.DIES, TriggerEvent.LEAVES_BATTLEFIELD) and graveyard_cards:
            cards_to_check.extend(graveyard_cards)

        for card in cards_to_check:
            for ability_def in card.card.triggered_abilities:
                trigger_event_name = ability_def.get("trigger", "")
                ability_event = _parse_trigger_event(trigger_event_name)

                if ability_event != event:
                    continue

                source_raw = ability_def.get("source", "self")
                source_filter = parse_source_filter(source_raw)
                if not _matches_filter(source_filter, card, event_data):
                    continue

                trigger = PendingTrigger(
                    ability=TriggeredAbility(
                        trigger=TriggerCondition(event=event, source_filter=source_filter),
                        effects=ability_def.get("effects", []),
                        source_card_id=card.instance_id,
                        controller_index=card.controller_index,
                    ),
                    source_card_id=card.instance_id,
                    controller_index=card.controller_index,
                    event_data=event_data,
                )
                triggered.append(trigger)

        self._pending.extend(triggered)
        return triggered


def _parse_trigger_event(name: str) -> TriggerEvent | None:
    """Map a string trigger name to a TriggerEvent."""
    mapping = {
        "enters_battlefield": TriggerEvent.ENTERS_BATTLEFIELD,
        "leaves_battlefield": TriggerEvent.LEAVES_BATTLEFIELD,
        "dies": TriggerEvent.DIES,
        "cast": TriggerEvent.CAST,
        "attacks": TriggerEvent.ATTACKS,
        "blocks": TriggerEvent.BLOCKS,
        "becomes_blocked": TriggerEvent.BECOMES_BLOCKED,
        "deals_combat_damage": TriggerEvent.DEALS_COMBAT_DAMAGE,
        "deals_combat_damage_to_player": TriggerEvent.DEALS_COMBAT_DAMAGE_TO_PLAYER,
        "begin_upkeep": TriggerEvent.BEGIN_UPKEEP,
        "begin_combat": TriggerEvent.BEGIN_COMBAT,
        "end_step": TriggerEvent.END_STEP,
        "gain_life": TriggerEvent.GAIN_LIFE,
        "lose_life": TriggerEvent.LOSE_LIFE,
        "draw_card": TriggerEvent.DRAW_CARD,
        "land_enters": TriggerEvent.LAND_ENTERS,
    }
    return mapping.get(name)


def _matches_filter(
    source_filter: dict[str, Any],
    card,
    event_data: dict[str, Any],
) -> bool:
    """Check if an event matches a structured source filter.

    Each key in the filter dict is checked independently; all must pass.

    Keys:
      - "relation": relationship between trigger owner and event source
          "self"    — event source is this card
          "another" — event source is NOT this card
          "any"     — always matches
          "you"     — event was caused by this card's controller
      - "card_type": event source must be this card type
          "creature", "artifact", "enchantment", "planeswalker",
          "land", "battle", "kindred"
          "permanent" — any permanent type (not instant/sorcery)
      - "token": True means only tokens, False means only non-tokens
    """
    from mtg_engine.core.enums import CardType

    _CARD_TYPE_MAP = {
        "creature": CardType.CREATURE,
        "artifact": CardType.ARTIFACT,
        "enchantment": CardType.ENCHANTMENT,
        "planeswalker": CardType.PLANESWALKER,
        "land": CardType.LAND,
        "battle": CardType.BATTLE,
        "kindred": CardType.KINDRED,
    }

    # Check relation
    relation = source_filter.get("relation")
    if relation == "self":
        if event_data.get("card_id") != card.instance_id:
            return False
    elif relation == "another":
        if event_data.get("card_id") == card.instance_id:
            return False
    elif relation == "you":
        if event_data.get("player_index") != card.controller_index:
            return False
    # "any" or no relation — always passes

    # Check card type
    card_type_filter = source_filter.get("card_type")
    if card_type_filter is not None:
        event_card = event_data.get("card")
        if event_card is None:
            return False
        if card_type_filter == "permanent":
            if event_card.card.card_type in (CardType.INSTANT, CardType.SORCERY):
                return False
        else:
            expected = _CARD_TYPE_MAP.get(card_type_filter)
            if expected is not None and event_card.card.card_type != expected:
                return False

    # Check token status
    token_filter = source_filter.get("token")
    if token_filter is not None:
        event_card = event_data.get("card")
        if event_card is None:
            return False
        is_token = getattr(event_card, "is_token", False)
        if token_filter and not is_token:
            return False
        if not token_filter and is_token:
            return False

    return True
