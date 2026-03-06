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


@dataclass
class TriggerCondition:
    """Defines when a triggered ability fires."""

    event: TriggerEvent
    # Optional filter: e.g., "self" (this card), "you" (controller),
    # "creature" (any creature), "nontoken" etc.
    source_filter: str = "self"
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
        if event == TriggerEvent.DIES and graveyard_cards:
            cards_to_check.extend(graveyard_cards)

        for card in cards_to_check:
            for ability_def in card.card.triggered_abilities:
                trigger_event_name = ability_def.get("trigger", "")
                ability_event = _parse_trigger_event(trigger_event_name)

                if ability_event != event:
                    continue

                source_filter = ability_def.get("source", "self")
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
    source_filter: str,
    card,
    event_data: dict[str, Any],
) -> bool:
    """Check if a card matches the source filter for a trigger."""
    if source_filter == "self":
        return event_data.get("card_id") == card.instance_id
    if source_filter == "any":
        return True
    if source_filter == "you":
        return event_data.get("player_index") == card.controller_index
    if source_filter == "creature":
        from mtg_engine.core.enums import CardType
        event_card = event_data.get("card")
        return event_card and event_card.card.card_type == CardType.CREATURE
    return True
