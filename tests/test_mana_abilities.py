"""Tests for mana abilities system."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Color, SuperType, Zone
from mtg_engine.core.game import Game
from mtg_engine.core.mana import ManaCost, ManaPool
from mtg_engine.core.mana_abilities import (
    BASIC_LAND_MANA,
    can_tap_for_mana,
    get_basic_land_mana,
    is_mana_ability,
    tap_all_lands_for_mana,
    tap_for_mana,
)


def _make_basic_land(name, subtype, owner=0):
    card = Card(
        name=name,
        card_type=CardType.LAND,
        supertypes=[SuperType.BASIC],
        subtypes=[subtype],
    )
    return CardInstance(card=card, zone=Zone.BATTLEFIELD, owner_index=owner, controller_index=owner)


class TestBasicLandMana:
    def test_get_basic_land_mana_forest(self):
        forest = _make_basic_land("Forest", "Forest")
        assert get_basic_land_mana(forest) == Color.GREEN

    def test_get_basic_land_mana_island(self):
        island = _make_basic_land("Island", "Island")
        assert get_basic_land_mana(island) == Color.BLUE

    def test_get_basic_land_mana_mountain(self):
        mountain = _make_basic_land("Mountain", "Mountain")
        assert get_basic_land_mana(mountain) == Color.RED

    def test_get_basic_land_mana_plains(self):
        plains = _make_basic_land("Plains", "Plains")
        assert get_basic_land_mana(plains) == Color.WHITE

    def test_get_basic_land_mana_swamp(self):
        swamp = _make_basic_land("Swamp", "Swamp")
        assert get_basic_land_mana(swamp) == Color.BLACK

    def test_nonbasic_land_no_inherent_mana(self):
        card = Card(name="Wasteland", card_type=CardType.LAND, subtypes=["Desert"])
        inst = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        assert get_basic_land_mana(inst) is None


class TestCanTapForMana:
    def test_untapped_land_can_tap(self):
        forest = _make_basic_land("Forest", "Forest")
        assert can_tap_for_mana(forest) is True

    def test_tapped_land_cant_tap(self):
        forest = _make_basic_land("Forest", "Forest")
        forest.tapped = True
        assert can_tap_for_mana(forest) is False

    def test_land_in_hand_cant_tap(self):
        forest = _make_basic_land("Forest", "Forest")
        forest.zone = Zone.HAND
        assert can_tap_for_mana(forest) is False


class TestTapForMana:
    def test_tap_forest_for_green(self):
        forest = _make_basic_land("Forest", "Forest")
        pool = ManaPool()
        color = tap_for_mana(forest, pool)
        assert color == Color.GREEN
        assert pool.green == 1
        assert forest.tapped is True

    def test_tap_island_for_blue(self):
        island = _make_basic_land("Island", "Island")
        pool = ManaPool()
        color = tap_for_mana(island, pool)
        assert color == Color.BLUE
        assert pool.blue == 1

    def test_cant_tap_already_tapped(self):
        forest = _make_basic_land("Forest", "Forest")
        forest.tapped = True
        pool = ManaPool()
        color = tap_for_mana(forest, pool)
        assert color is None
        assert pool.green == 0


class TestTapAllLands:
    def test_tap_multiple_lands(self):
        forest1 = _make_basic_land("Forest", "Forest")
        forest2 = _make_basic_land("Forest", "Forest")
        mountain = _make_basic_land("Mountain", "Mountain")
        pool = ManaPool()

        produced = tap_all_lands_for_mana([forest1, forest2, mountain], pool)
        assert pool.green == 2
        assert pool.red == 1
        assert len(produced) == 3

    def test_skips_tapped_lands(self):
        forest = _make_basic_land("Forest", "Forest")
        tapped_forest = _make_basic_land("Forest", "Forest")
        tapped_forest.tapped = True
        pool = ManaPool()

        produced = tap_all_lands_for_mana([forest, tapped_forest], pool)
        assert pool.green == 1
        assert len(produced) == 1


class TestIsManaAbility:
    def test_add_mana_is_mana_ability(self):
        ability = {
            "effects": [{"type": "add_mana", "color": "G"}],
            "has_target": False,
        }
        assert is_mana_ability(ability) is True

    def test_loyalty_not_mana_ability(self):
        ability = {
            "effects": [{"type": "add_mana", "color": "G"}],
            "is_loyalty": True,
        }
        assert is_mana_ability(ability) is False

    def test_targeted_not_mana_ability(self):
        ability = {
            "effects": [{"type": "add_mana", "color": "G"}],
            "has_target": True,
        }
        assert is_mana_ability(ability) is False


class TestGameManaAbilities:
    def test_tap_land_in_game(self):
        forest = Card(
            name="Forest",
            card_type=CardType.LAND,
            supertypes=[SuperType.BASIC],
            subtypes=["Forest"],
        )
        game = Game(["Alice", "Bob"], [[forest], []])
        forest_inst = game.state.cards[0]
        forest_inst.zone = Zone.BATTLEFIELD

        result = game.tap_land_for_mana(0, forest_inst.instance_id)
        assert result is True
        assert game.state.players[0].mana_pool.green == 1
        assert forest_inst.tapped is True

    def test_cant_tap_opponents_land(self):
        forest = Card(
            name="Forest",
            card_type=CardType.LAND,
            supertypes=[SuperType.BASIC],
            subtypes=["Forest"],
        )
        game = Game(["Alice", "Bob"], [[], [forest]])
        forest_inst = game.state.cards[0]
        forest_inst.zone = Zone.BATTLEFIELD

        result = game.tap_land_for_mana(0, forest_inst.instance_id)
        assert result is False
