"""Tests for Adventure cards."""

import pytest

from mtg_engine.core.adventure import (
    AdventureData,
    AdventureState,
    can_cast_adventure,
    can_cast_from_adventure,
    cast_as_adventure,
    cast_creature_from_adventure,
    get_adventure,
    has_adventure,
    is_on_adventure,
    resolve_adventure,
    setup_adventure,
)
from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.mana import ManaCost


def _make_bonecrusher():
    """Bonecrusher Giant / Stomp."""
    creature = Card(
        name="Bonecrusher Giant",
        card_type=CardType.CREATURE,
        cost=ManaCost.parse("{2}{R}"),
        power=4,
        toughness=3,
    )
    adventure = AdventureData(
        name="Stomp",
        card_type=CardType.INSTANT,
        cost=ManaCost.parse("{1}{R}"),
        effects=[{"type": "damage", "target": {"kind": "target"}, "amount": 2}],
    )
    return creature, adventure


class TestSetupAdventure:
    def test_setup(self):
        creature, adventure = _make_bonecrusher()
        instance = CardInstance(card=creature, zone=Zone.HAND)
        setup_adventure(instance, adventure)

        assert has_adventure(instance)
        adv = get_adventure(instance)
        assert adv is not None
        assert adv.name == "Stomp"
        assert adv.card_type == CardType.INSTANT

    def test_no_adventure_by_default(self):
        creature, _ = _make_bonecrusher()
        instance = CardInstance(card=creature, zone=Zone.HAND)
        assert not has_adventure(instance)


class TestCastAdventure:
    def test_can_cast_from_hand(self):
        creature, adventure = _make_bonecrusher()
        instance = CardInstance(card=creature, zone=Zone.HAND)
        setup_adventure(instance, adventure)

        assert can_cast_adventure(instance)

    def test_cannot_cast_from_battlefield(self):
        creature, adventure = _make_bonecrusher()
        instance = CardInstance(card=creature, zone=Zone.BATTLEFIELD)
        setup_adventure(instance, adventure)

        assert not can_cast_adventure(instance)

    def test_cast_as_adventure(self):
        creature, adventure = _make_bonecrusher()
        instance = CardInstance(card=creature, zone=Zone.HAND)
        setup_adventure(instance, adventure)

        adv = cast_as_adventure(instance)
        assert adv is not None
        assert adv.name == "Stomp"
        # Card should now reflect adventure characteristics
        assert instance.card.name == "Stomp"
        assert instance.card.card_type == CardType.INSTANT


class TestResolveAdventure:
    def test_resolve_goes_to_exile(self):
        creature, adventure = _make_bonecrusher()
        instance = CardInstance(card=creature, zone=Zone.HAND)
        setup_adventure(instance, adventure)

        cast_as_adventure(instance)
        result = resolve_adventure(instance)

        assert result is True
        assert instance.zone == Zone.EXILE
        assert is_on_adventure(instance)
        # Card should be restored to creature
        assert instance.card.name == "Bonecrusher Giant"

    def test_cannot_resolve_if_not_cast_as_adventure(self):
        creature, adventure = _make_bonecrusher()
        instance = CardInstance(card=creature, zone=Zone.HAND)
        setup_adventure(instance, adventure)

        result = resolve_adventure(instance)
        assert result is False


class TestCastFromAdventure:
    def test_can_cast_from_exile(self):
        creature, adventure = _make_bonecrusher()
        instance = CardInstance(card=creature, zone=Zone.HAND)
        setup_adventure(instance, adventure)

        cast_as_adventure(instance)
        resolve_adventure(instance)

        assert can_cast_from_adventure(instance)

    def test_cast_creature_from_exile(self):
        creature, adventure = _make_bonecrusher()
        instance = CardInstance(card=creature, zone=Zone.HAND)
        setup_adventure(instance, adventure)

        cast_as_adventure(instance)
        resolve_adventure(instance)
        result = cast_creature_from_adventure(instance)

        assert result is True
        assert not is_on_adventure(instance)
        assert instance.card.name == "Bonecrusher Giant"
        assert instance.card.card_type == CardType.CREATURE
        assert instance.card.power == 4

    def test_cannot_cast_if_not_on_adventure(self):
        creature, adventure = _make_bonecrusher()
        instance = CardInstance(card=creature, zone=Zone.EXILE)
        setup_adventure(instance, adventure)

        assert not can_cast_from_adventure(instance)


class TestAdventureEdgeCases:
    def test_cannot_adventure_twice(self):
        creature, adventure = _make_bonecrusher()
        instance = CardInstance(card=creature, zone=Zone.HAND)
        setup_adventure(instance, adventure)

        cast_as_adventure(instance)
        resolve_adventure(instance)

        # On adventure in exile — cannot cast adventure again
        assert not can_cast_adventure(instance)
