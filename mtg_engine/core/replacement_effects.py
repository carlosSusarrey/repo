"""Replacement effects system.

CR 614: Replacement effects modify events as they happen.
"If [event] would [happen], instead [alternative]."

Key rules:
- CR 614.5: Only one replacement effect can apply to any given event
- CR 614.6: If multiple could apply, affected player/controller chooses
- CR 614.7: Prevention effects are a subset of replacement effects
- CR 616.1: Self-replacement effects apply first
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable


class ReplacementType(Enum):
    """Types of events that can be replaced."""
    DAMAGE = auto()           # "If damage would be dealt..."
    DRAW = auto()             # "If you would draw a card..."
    ENTER_BATTLEFIELD = auto()  # "If ~ would enter the battlefield..."
    DIE = auto()              # "If ~ would die..."
    DISCARD = auto()          # "If you would discard..."
    COUNTER_PLACED = auto()   # "If a counter would be placed..."
    LIFE_GAIN = auto()        # "If you would gain life..."
    ZONE_CHANGE = auto()      # Generic zone change replacement


@dataclass
class ReplacementEffect:
    """A replacement effect that modifies an event before it happens.

    CR 614: "Instead" effects replace events as they happen.
    """
    source_id: str
    replacement_type: ReplacementType
    timestamp: int = 0

    # Condition for when this replacement applies
    # Returns True if this replacement should apply to the given event
    condition: Callable[[dict[str, Any]], bool] | None = None

    # What to do instead (modifier function)
    # Takes the event dict, returns modified event dict (or None to prevent)
    apply: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None

    # Simple replacements (used when apply is None)
    prevent: bool = False          # Prevent the event entirely
    modify_amount: int | None = None  # Change amount (e.g., damage)
    redirect_to: str | None = None    # Redirect target
    add_counters: dict[str, int] = field(default_factory=dict)  # Add counters on ETB
    enter_tapped: bool = False     # Enter the battlefield tapped

    # Whether this is a self-replacement (applies first per CR 614.16d)
    is_self_replacement: bool = False

    # Controller who decides if multiple replacements apply
    controller_index: int = 0


class ReplacementEffectManager:
    """Manages all active replacement effects."""

    def __init__(self) -> None:
        self._effects: list[ReplacementEffect] = []
        self._timestamp: int = 0

    def add_effect(self, effect: ReplacementEffect) -> None:
        """Add a new replacement effect."""
        self._timestamp += 1
        effect.timestamp = self._timestamp
        self._effects.append(effect)

    def remove_effects_from(self, source_id: str) -> None:
        """Remove all replacement effects from a given source."""
        self._effects = [e for e in self._effects if e.source_id != source_id]

    @property
    def effects(self) -> list[ReplacementEffect]:
        return list(self._effects)

    def check_replacement(
        self,
        event_type: ReplacementType,
        event: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Check if any replacement effects apply to an event.

        Returns the modified event dict, or None if the event is prevented.
        Self-replacement effects apply first (CR 614.16d).
        """
        applicable = [
            e for e in self._effects
            if e.replacement_type == event_type
            and (e.condition is None or e.condition(event))
        ]

        if not applicable:
            return event

        # Self-replacement effects apply first
        self_replacements = [e for e in applicable if e.is_self_replacement]
        other_replacements = [e for e in applicable if not e.is_self_replacement]

        # Apply self-replacements first
        current_event = dict(event)
        for effect in self_replacements:
            result = self._apply_effect(effect, current_event)
            if result is None:
                return None
            current_event = result

        # Then apply one other replacement (CR 614.5: only one)
        if other_replacements:
            # If multiple, use the first (in real game, affected player chooses)
            effect = other_replacements[0]
            result = self._apply_effect(effect, current_event)
            if result is None:
                return None
            current_event = result

        return current_event

    def _apply_effect(
        self,
        effect: ReplacementEffect,
        event: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Apply a single replacement effect to an event."""
        if effect.prevent:
            return None

        if effect.apply is not None:
            return effect.apply(event)

        result = dict(event)

        if effect.modify_amount is not None:
            result["amount"] = effect.modify_amount

        if effect.redirect_to is not None:
            result["target"] = effect.redirect_to

        if effect.add_counters:
            existing = result.get("counters", {})
            for counter_type, count in effect.add_counters.items():
                existing[counter_type] = existing.get(counter_type, 0) + count
            result["counters"] = existing

        if effect.enter_tapped:
            result["enters_tapped"] = True

        return result


# --- Helper constructors ---

def create_prevention_effect(
    source_id: str,
    controller_index: int = 0,
    prevent_amount: int | None = None,
    condition: Callable[[dict[str, Any]], bool] | None = None,
) -> ReplacementEffect:
    """Create a damage prevention effect.

    If prevent_amount is None, prevents all damage.
    Otherwise prevents up to that much damage.
    """
    if prevent_amount is None:
        return ReplacementEffect(
            source_id=source_id,
            replacement_type=ReplacementType.DAMAGE,
            prevent=True,
            condition=condition,
            controller_index=controller_index,
        )

    def reduce_damage(event: dict[str, Any]) -> dict[str, Any] | None:
        amount = event.get("amount", 0)
        reduced = max(0, amount - prevent_amount)
        if reduced == 0:
            return None
        return {**event, "amount": reduced}

    return ReplacementEffect(
        source_id=source_id,
        replacement_type=ReplacementType.DAMAGE,
        apply=reduce_damage,
        condition=condition,
        controller_index=controller_index,
    )


def create_etb_with_counters(
    source_id: str,
    counter_type: str,
    count: int,
) -> ReplacementEffect:
    """Create an ETB replacement that adds counters (e.g., 'enters with N +1/+1 counters')."""
    def condition(event: dict[str, Any]) -> bool:
        return event.get("card_id") == source_id

    return ReplacementEffect(
        source_id=source_id,
        replacement_type=ReplacementType.ENTER_BATTLEFIELD,
        add_counters={counter_type: count},
        condition=condition,
        is_self_replacement=True,
        controller_index=0,
    )


def create_etb_tapped(
    source_id: str,
) -> ReplacementEffect:
    """Create an ETB replacement that makes the permanent enter tapped."""
    def condition(event: dict[str, Any]) -> bool:
        return event.get("card_id") == source_id

    return ReplacementEffect(
        source_id=source_id,
        replacement_type=ReplacementType.ENTER_BATTLEFIELD,
        enter_tapped=True,
        condition=condition,
        is_self_replacement=True,
        controller_index=0,
    )


def create_damage_redirect(
    source_id: str,
    redirect_to: str,
    condition: Callable[[dict[str, Any]], bool] | None = None,
    controller_index: int = 0,
) -> ReplacementEffect:
    """Create a damage redirection effect."""
    return ReplacementEffect(
        source_id=source_id,
        replacement_type=ReplacementType.DAMAGE,
        redirect_to=redirect_to,
        condition=condition,
        controller_index=controller_index,
    )


def create_life_gain_replacement(
    source_id: str,
    apply_fn: Callable[[dict[str, Any]], dict[str, Any] | None],
    condition: Callable[[dict[str, Any]], bool] | None = None,
    controller_index: int = 0,
) -> ReplacementEffect:
    """Create a life gain replacement effect (e.g., Tainted Remedy, doubling)."""
    return ReplacementEffect(
        source_id=source_id,
        replacement_type=ReplacementType.LIFE_GAIN,
        apply=apply_fn,
        condition=condition,
        controller_index=controller_index,
    )


def create_draw_replacement(
    source_id: str,
    apply_fn: Callable[[dict[str, Any]], dict[str, Any] | None],
    condition: Callable[[dict[str, Any]], bool] | None = None,
    controller_index: int = 0,
) -> ReplacementEffect:
    """Create a draw replacement effect (e.g., dredge, replacement with mill)."""
    return ReplacementEffect(
        source_id=source_id,
        replacement_type=ReplacementType.DRAW,
        apply=apply_fn,
        condition=condition,
        controller_index=controller_index,
    )
