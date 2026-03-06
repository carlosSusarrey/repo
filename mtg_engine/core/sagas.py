"""Sagas and Class enchantments.

CR 714: Saga cards are enchantments with chapter abilities.
They enter with a lore counter, gain one each draw step,
and trigger chapter abilities when lore counters reach thresholds.
After the final chapter ability resolves and leaves the stack,
the saga is sacrificed (SBA).

CR 716: Class enchantments have levels that can be activated
in order at sorcery speed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChapterAbility:
    """A chapter ability on a saga."""
    chapter: int           # Which chapter number (1, 2, 3, etc.)
    effects: list[dict[str, Any]] = field(default_factory=list)
    description: str = ""


@dataclass
class SagaState:
    """Tracks saga state on a card instance."""
    chapters: list[ChapterAbility] = field(default_factory=list)
    final_chapter: int = 0
    triggered_chapters: set[int] = field(default_factory=set)

    @property
    def lore_counters(self) -> int:
        """Get current lore counter count (stored on the card instance)."""
        return len(self.triggered_chapters)


def setup_saga(
    card_instance: Any,  # CardInstance
    chapters: list[ChapterAbility],
) -> None:
    """Set up a card instance as a saga with chapter abilities.

    CR 714.3a: A saga enters with a lore counter.
    """
    final = max(ch.chapter for ch in chapters) if chapters else 1
    state = SagaState(chapters=chapters, final_chapter=final)
    card_instance._saga_state = state  # type: ignore[attr-defined]
    card_instance.counters["lore"] = 1
    state.triggered_chapters.add(0)  # Mark initialization


def add_lore_counter(card_instance: Any) -> list[dict[str, Any]]:
    """Add a lore counter to a saga and return any triggered chapter effects.

    CR 714.3b: After your draw step, add a lore counter.
    Triggered abilities go on the stack.
    """
    state = getattr(card_instance, '_saga_state', None)
    if state is None:
        return []

    current = card_instance.counters.get("lore", 0)
    current += 1
    card_instance.counters["lore"] = current

    # Check which chapters trigger
    triggered_effects = []
    for chapter in state.chapters:
        if chapter.chapter == current and current not in state.triggered_chapters:
            state.triggered_chapters.add(current)
            triggered_effects.extend(chapter.effects)

    return triggered_effects


def get_saga_chapter(card_instance: Any) -> int:
    """Get the current chapter number (based on lore counters)."""
    return card_instance.counters.get("lore", 0)


def is_saga_complete(card_instance: Any) -> bool:
    """Check if a saga has reached its final chapter.

    CR 714.4: After the final chapter ability has resolved and left
    the stack, the saga is sacrificed (SBA).
    """
    state = getattr(card_instance, '_saga_state', None)
    if state is None:
        return False
    return card_instance.counters.get("lore", 0) >= state.final_chapter


def trigger_chapter(card_instance: Any, chapter_num: int) -> list[dict[str, Any]]:
    """Manually trigger a specific chapter's effects."""
    state = getattr(card_instance, '_saga_state', None)
    if state is None:
        return []

    for chapter in state.chapters:
        if chapter.chapter == chapter_num:
            state.triggered_chapters.add(chapter_num)
            return list(chapter.effects)
    return []


def is_saga(card_instance: Any) -> bool:
    """Check if a card instance is a saga."""
    return getattr(card_instance, '_saga_state', None) is not None


# --- Class Enchantments ---

@dataclass
class ClassLevel:
    """A level on a class enchantment."""
    level: int
    cost: str              # Mana cost to activate this level
    effects: list[dict[str, Any]] = field(default_factory=list)
    static_abilities: list[dict[str, Any]] = field(default_factory=list)
    description: str = ""


@dataclass
class ClassState:
    """Tracks class enchantment state."""
    levels: list[ClassLevel] = field(default_factory=list)
    current_level: int = 1
    max_level: int = 3


def setup_class(
    card_instance: Any,
    levels: list[ClassLevel],
) -> None:
    """Set up a card instance as a class enchantment."""
    max_lvl = max(lv.level for lv in levels) if levels else 1
    state = ClassState(levels=levels, max_level=max_lvl)
    card_instance._class_state = state  # type: ignore[attr-defined]


def can_level_up(card_instance: Any) -> bool:
    """Check if a class enchantment can be leveled up.

    CR 716.3: Level up is a sorcery-speed activated ability.
    Levels must be gained in order.
    """
    state = getattr(card_instance, '_class_state', None)
    if state is None:
        return False
    return state.current_level < state.max_level


def level_up(card_instance: Any) -> list[dict[str, Any]]:
    """Level up a class enchantment. Returns effects gained.

    CR 716.3: You gain the abilities of the next level.
    """
    state = getattr(card_instance, '_class_state', None)
    if state is None:
        return []
    if state.current_level >= state.max_level:
        return []

    state.current_level += 1

    # Get the effects for the new level
    for level in state.levels:
        if level.level == state.current_level:
            return list(level.effects)
    return []


def get_class_level(card_instance: Any) -> int:
    """Get the current level of a class enchantment."""
    state = getattr(card_instance, '_class_state', None)
    if state is None:
        return 0
    return state.current_level


def get_class_level_cost(card_instance: Any) -> str | None:
    """Get the cost to reach the next level."""
    state = getattr(card_instance, '_class_state', None)
    if state is None:
        return None
    next_level = state.current_level + 1
    for level in state.levels:
        if level.level == next_level:
            return level.cost
    return None


def is_class(card_instance: Any) -> bool:
    """Check if a card instance is a class enchantment."""
    return getattr(card_instance, '_class_state', None) is not None
