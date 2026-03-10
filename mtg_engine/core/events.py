"""Centralized game event system.

Provides a unified GameEvent enum and typed event data classes that replace
the separate TriggerEvent and ReplacementType enums.  An EventBus dispatches
events to both the trigger and replacement-effect managers through a single
``emit()`` call, eliminating hand-built dicts scattered across the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


# ---------------------------------------------------------------------------
# Unified event enum
# ---------------------------------------------------------------------------

class GameEvent(Enum):
    """Every game event that can fire triggers or be replaced."""

    # Zone changes
    ENTERS_BATTLEFIELD = auto()
    LEAVES_BATTLEFIELD = auto()
    DIES = auto()
    ENTERS_GRAVEYARD = auto()
    IS_EXILED = auto()
    ENTERS_HAND = auto()
    PUT_ON_TOP_LIBRARY = auto()
    PUT_ON_BOTTOM_LIBRARY = auto()
    ZONE_CHANGE = auto()

    # Spells
    CAST = auto()

    # Combat
    ATTACKS = auto()
    BLOCKS = auto()
    BECOMES_BLOCKED = auto()
    DEALS_COMBAT_DAMAGE = auto()
    DEALS_COMBAT_DAMAGE_TO_PLAYER = auto()

    # Phase / step
    BEGIN_UPKEEP = auto()
    BEGIN_COMBAT = auto()
    END_STEP = auto()

    # Resources
    GAIN_LIFE = auto()
    LOSE_LIFE = auto()
    DRAW_CARD = auto()
    LAND_ENTERS = auto()
    DAMAGE = auto()
    DISCARD = auto()
    COUNTER_PLACED = auto()


# ---------------------------------------------------------------------------
# Typed event-data classes
# ---------------------------------------------------------------------------

@dataclass
class EventData:
    """Base for all event payloads. Provides dict round-tripping."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for backward compat with managers."""
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EventData":
        """Reconstruct from a dict (best-effort, ignores unknown keys)."""
        import inspect
        valid = {k for k in inspect.signature(cls).parameters}
        return cls(**{k: v for k, v in d.items() if k in valid})


@dataclass
class ZoneChangeEventData(EventData):
    card_id: str = ""
    card: Any = None  # CardInstance
    player_index: int = 0
    from_zone: Any = None  # Zone | None
    to_zone: Any = None    # Zone | None
    cause: str = ""


@dataclass
class DamageEventData(EventData):
    source_id: str = ""
    target: str = ""       # player name or card instance_id
    amount: int = 0
    is_combat: bool = False


@dataclass
class LifeEventData(EventData):
    player_index: int = 0
    amount: int = 0


@dataclass
class SpellEventData(EventData):
    card_id: str = ""
    card: Any = None
    player_index: int = 0


@dataclass
class CombatEventData(EventData):
    card_id: str = ""
    card: Any = None
    player_index: int = 0
    amount: int = 0


@dataclass
class DrawEventData(EventData):
    player_index: int = 0


@dataclass
class PhaseEventData(EventData):
    player_index: int = 0


@dataclass
class CounterEventData(EventData):
    card_id: str = ""
    card: Any = None
    counter_type: str = ""
    amount: int = 0
    player_index: int = 0


# ---------------------------------------------------------------------------
# Mappings between GameEvent and the legacy enum members
# ---------------------------------------------------------------------------

# Lazy imports to avoid circular dependencies — the mappings are built on
# first access via the functions below.

_trigger_map: dict[GameEvent, Any] | None = None
_replacement_map: dict[GameEvent, Any] | None = None


def _game_event_to_trigger(event: GameEvent):
    """Map a GameEvent to the legacy TriggerEvent member (same name)."""
    global _trigger_map
    if _trigger_map is None:
        from mtg_engine.core.triggers import TriggerEvent
        _trigger_map = {}
        for ge in GameEvent:
            try:
                _trigger_map[ge] = TriggerEvent[ge.name]
            except KeyError:
                pass
    return _trigger_map.get(event)


def _game_event_to_replacement(event: GameEvent):
    """Map a GameEvent to the legacy ReplacementType member."""
    global _replacement_map
    if _replacement_map is None:
        from mtg_engine.core.replacement_effects import ReplacementType
        _replacement_map = {
            GameEvent.ENTERS_BATTLEFIELD: ReplacementType.ENTER_BATTLEFIELD,
            GameEvent.DIES: ReplacementType.DIE,
            GameEvent.DAMAGE: ReplacementType.DAMAGE,
            GameEvent.DRAW_CARD: ReplacementType.DRAW,
            GameEvent.GAIN_LIFE: ReplacementType.LIFE_GAIN,
            GameEvent.DISCARD: ReplacementType.DISCARD,
            GameEvent.COUNTER_PLACED: ReplacementType.COUNTER_PLACED,
            GameEvent.ZONE_CHANGE: ReplacementType.ZONE_CHANGE,
        }
    return _replacement_map.get(event)


# The set of GameEvents that have a corresponding ReplacementType.
_REPLACEABLE_EVENTS: frozenset[GameEvent] = frozenset({
    GameEvent.ENTERS_BATTLEFIELD,
    GameEvent.DIES,
    GameEvent.DAMAGE,
    GameEvent.DRAW_CARD,
    GameEvent.GAIN_LIFE,
    GameEvent.DISCARD,
    GameEvent.COUNTER_PLACED,
    GameEvent.ZONE_CHANGE,
})


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

class EventBus:
    """Central event dispatcher.

    Routes every game event through replacement effects first (when
    applicable), then fires triggered-ability checks.  Call sites use a
    single ``emit()`` instead of manually building dicts and calling two
    separate managers.
    """

    def __init__(self, trigger_manager, replacement_manager) -> None:
        self._triggers = trigger_manager
        self._replacements = replacement_manager

    # -- public API --

    def emit(
        self,
        event: GameEvent,
        data: EventData | dict[str, Any],
        battlefield_cards: list,
        extra_cards: list | None = None,
    ) -> dict[str, Any] | None:
        """Emit a game event.

        1. If the event is replaceable, check replacement effects first.
           If the event is fully prevented (replacement returns ``None``),
           return ``None`` immediately — no triggers fire.
        2. Otherwise, check triggered abilities.

        Returns the (possibly modified) event data dict, or ``None`` if
        the event was prevented by a replacement effect.
        """
        data_dict = data.to_dict() if isinstance(data, EventData) else dict(data)

        # 1. Replacement effects
        if event in _REPLACEABLE_EVENTS:
            repl_type = _game_event_to_replacement(event)
            if repl_type is not None:
                result = self._replacements.check_replacement(repl_type, data_dict)
                if result is None:
                    return None
                data_dict = result

        # 2. Triggered abilities
        trigger_event = _game_event_to_trigger(event)
        if trigger_event is not None:
            self._triggers.check_triggers(
                trigger_event, data_dict, battlefield_cards, extra_cards,
            )

        return data_dict

    def emit_replacement_only(
        self,
        event: GameEvent,
        data: EventData | dict[str, Any],
    ) -> dict[str, Any] | None:
        """Check replacement effects without firing triggers.

        Useful when the caller needs the replacement result before deciding
        whether to proceed (e.g. ETB modifications applied to a card before
        placing it, or die-replacement that prevents the zone move).
        """
        data_dict = data.to_dict() if isinstance(data, EventData) else dict(data)
        repl_type = _game_event_to_replacement(event)
        if repl_type is None:
            return data_dict
        return self._replacements.check_replacement(repl_type, data_dict)

    def emit_triggers_only(
        self,
        event: GameEvent,
        data: EventData | dict[str, Any],
        battlefield_cards: list,
        extra_cards: list | None = None,
    ) -> None:
        """Fire triggers without checking replacement effects.

        Useful for events that have already been through replacement
        (e.g. zone-destination triggers after move_card).
        """
        data_dict = data.to_dict() if isinstance(data, EventData) else dict(data)
        trigger_event = _game_event_to_trigger(event)
        if trigger_event is not None:
            self._triggers.check_triggers(
                trigger_event, data_dict, battlefield_cards, extra_cards,
            )
