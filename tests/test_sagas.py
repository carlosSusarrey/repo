"""Tests for Sagas and Class enchantments."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.mana import ManaCost
from mtg_engine.core.sagas import (
    ChapterAbility,
    ClassLevel,
    ClassState,
    SagaState,
    add_lore_counter,
    can_level_up,
    get_class_level,
    get_class_level_cost,
    get_saga_chapter,
    is_class,
    is_saga,
    is_saga_complete,
    level_up,
    setup_class,
    setup_saga,
    trigger_chapter,
)


def _make_saga_card():
    return Card(
        name="The Eldest Reborn",
        card_type=CardType.ENCHANTMENT,
        cost=ManaCost.parse("{4}{B}"),
        subtypes=["Saga"],
    )


def _make_class_card():
    return Card(
        name="Ranger Class",
        card_type=CardType.ENCHANTMENT,
        cost=ManaCost.parse("{1}{G}"),
        subtypes=["Class"],
    )


class TestSagaSetup:
    def test_setup_saga(self):
        card = _make_saga_card()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)

        chapters = [
            ChapterAbility(chapter=1, effects=[{"type": "sacrifice"}]),
            ChapterAbility(chapter=2, effects=[{"type": "draw", "amount": 1}]),
            ChapterAbility(chapter=3, effects=[{"type": "reanimate"}]),
        ]
        setup_saga(instance, chapters)

        assert is_saga(instance)
        assert instance.counters["lore"] == 1
        assert get_saga_chapter(instance) == 1

    def test_not_saga_by_default(self):
        card = _make_saga_card()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        assert not is_saga(instance)


class TestSagaProgression:
    def _setup_three_chapter_saga(self):
        card = _make_saga_card()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        chapters = [
            ChapterAbility(chapter=1, effects=[{"type": "effect1"}]),
            ChapterAbility(chapter=2, effects=[{"type": "effect2"}]),
            ChapterAbility(chapter=3, effects=[{"type": "effect3"}]),
        ]
        setup_saga(instance, chapters)
        return instance

    def test_add_lore_counter(self):
        instance = self._setup_three_chapter_saga()
        assert get_saga_chapter(instance) == 1

        effects = add_lore_counter(instance)
        assert get_saga_chapter(instance) == 2
        assert len(effects) == 1
        assert effects[0]["type"] == "effect2"

    def test_progress_to_final(self):
        instance = self._setup_three_chapter_saga()

        add_lore_counter(instance)  # Chapter 2
        effects = add_lore_counter(instance)  # Chapter 3
        assert get_saga_chapter(instance) == 3
        assert effects[0]["type"] == "effect3"
        assert is_saga_complete(instance)

    def test_not_complete_before_final(self):
        instance = self._setup_three_chapter_saga()
        assert not is_saga_complete(instance)
        add_lore_counter(instance)
        assert not is_saga_complete(instance)


class TestTriggerChapter:
    def test_trigger_specific_chapter(self):
        card = _make_saga_card()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        chapters = [
            ChapterAbility(chapter=1, effects=[{"type": "draw", "amount": 1}]),
            ChapterAbility(chapter=2, effects=[{"type": "mill", "amount": 3}]),
        ]
        setup_saga(instance, chapters)

        effects = trigger_chapter(instance, 2)
        assert len(effects) == 1
        assert effects[0]["type"] == "mill"

    def test_trigger_nonexistent_chapter(self):
        card = _make_saga_card()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        chapters = [ChapterAbility(chapter=1, effects=[{"type": "draw"}])]
        setup_saga(instance, chapters)

        effects = trigger_chapter(instance, 5)
        assert len(effects) == 0


class TestClassSetup:
    def test_setup_class(self):
        card = _make_class_card()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)

        levels = [
            ClassLevel(level=1, cost="{0}", effects=[{"type": "create_token"}]),
            ClassLevel(level=2, cost="{1}{G}", effects=[{"type": "pump"}]),
            ClassLevel(level=3, cost="{3}{G}", effects=[{"type": "anthem"}]),
        ]
        setup_class(instance, levels)

        assert is_class(instance)
        assert get_class_level(instance) == 1

    def test_not_class_by_default(self):
        card = _make_class_card()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        assert not is_class(instance)


class TestClassProgression:
    def _setup_class(self):
        card = _make_class_card()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        levels = [
            ClassLevel(level=1, cost="{0}", effects=[{"type": "token"}]),
            ClassLevel(level=2, cost="{1}{G}", effects=[{"type": "pump"}]),
            ClassLevel(level=3, cost="{3}{G}", effects=[{"type": "anthem"}]),
        ]
        setup_class(instance, levels)
        return instance

    def test_can_level_up(self):
        instance = self._setup_class()
        assert can_level_up(instance)

    def test_level_up(self):
        instance = self._setup_class()

        effects = level_up(instance)
        assert get_class_level(instance) == 2
        assert len(effects) == 1
        assert effects[0]["type"] == "pump"

    def test_level_up_to_max(self):
        instance = self._setup_class()
        level_up(instance)  # -> 2
        effects = level_up(instance)  # -> 3
        assert get_class_level(instance) == 3
        assert effects[0]["type"] == "anthem"
        assert not can_level_up(instance)

    def test_cannot_level_past_max(self):
        instance = self._setup_class()
        level_up(instance)  # -> 2
        level_up(instance)  # -> 3
        effects = level_up(instance)  # Should do nothing
        assert get_class_level(instance) == 3
        assert len(effects) == 0

    def test_get_level_cost(self):
        instance = self._setup_class()
        cost = get_class_level_cost(instance)
        assert cost == "{1}{G}"  # Cost to go from level 1 -> 2
