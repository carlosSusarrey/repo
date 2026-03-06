"""Tests for Planeswalker loyalty abilities."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone, Step, SuperType
from mtg_engine.core.game import Game
from mtg_engine.core.mana import ManaCost
from mtg_engine.core.planeswalker import (
    activate_loyalty,
    can_activate_loyalty,
    get_loyalty,
    initialize_loyalty,
    set_loyalty,
)


def _make_planeswalker(name="Jace", loyalty=3, abilities=None):
    card = Card(
        name=name,
        card_type=CardType.PLANESWALKER,
        loyalty=loyalty,
        supertypes=[SuperType.LEGENDARY],
        activated_abilities=abilities or [
            {"loyalty_cost": 1, "is_loyalty": True, "effects": [{"type": "draw", "amount": 1}]},
            {"loyalty_cost": -2, "is_loyalty": True, "effects": [{"type": "damage", "amount": 2}]},
        ],
    )
    inst = CardInstance(card=card, zone=Zone.BATTLEFIELD, owner_index=0, controller_index=0)
    return inst


class TestLoyalty:
    def test_initialize_loyalty(self):
        pw = _make_planeswalker(loyalty=4)
        initialize_loyalty(pw)
        assert get_loyalty(pw) == 4

    def test_set_loyalty(self):
        pw = _make_planeswalker(loyalty=3)
        initialize_loyalty(pw)
        set_loyalty(pw, 5)
        assert get_loyalty(pw) == 5

    def test_loyalty_cant_go_negative(self):
        pw = _make_planeswalker(loyalty=3)
        initialize_loyalty(pw)
        set_loyalty(pw, -1)
        assert get_loyalty(pw) == 0


class TestCanActivateLoyalty:
    def test_can_activate_plus(self):
        pw = _make_planeswalker(loyalty=3)
        initialize_loyalty(pw)
        activated = set()
        assert can_activate_loyalty(pw, 0, activated) is True

    def test_can_activate_minus(self):
        pw = _make_planeswalker(loyalty=3)
        initialize_loyalty(pw)
        activated = set()
        assert can_activate_loyalty(pw, 1, activated) is True

    def test_cant_activate_twice_per_turn(self):
        pw = _make_planeswalker(loyalty=3)
        initialize_loyalty(pw)
        activated = set()
        activate_loyalty(pw, 0, activated)
        assert can_activate_loyalty(pw, 1, activated) is False

    def test_cant_activate_if_loyalty_too_low(self):
        pw = _make_planeswalker(loyalty=1, abilities=[
            {"loyalty_cost": -3, "is_loyalty": True, "effects": [{"type": "draw", "amount": 1}]},
        ])
        initialize_loyalty(pw)
        activated = set()
        assert can_activate_loyalty(pw, 0, activated) is False

    def test_cant_activate_from_graveyard(self):
        pw = _make_planeswalker(loyalty=3)
        pw.zone = Zone.GRAVEYARD
        initialize_loyalty(pw)
        activated = set()
        assert can_activate_loyalty(pw, 0, activated) is False


class TestActivateLoyalty:
    def test_plus_ability_adds_loyalty(self):
        pw = _make_planeswalker(loyalty=3)
        initialize_loyalty(pw)
        activated = set()
        result = activate_loyalty(pw, 0, activated)
        assert result is not None
        assert get_loyalty(pw) == 4  # 3 + 1

    def test_minus_ability_removes_loyalty(self):
        pw = _make_planeswalker(loyalty=3)
        initialize_loyalty(pw)
        activated = set()
        result = activate_loyalty(pw, 1, activated)
        assert result is not None
        assert get_loyalty(pw) == 1  # 3 - 2

    def test_activate_returns_effects(self):
        pw = _make_planeswalker(loyalty=3)
        initialize_loyalty(pw)
        activated = set()
        result = activate_loyalty(pw, 0, activated)
        assert result is not None
        assert len(result["effects"]) == 1
        assert result["effects"][0]["type"] == "draw"


class TestPlaneswalkerInGame:
    def test_planeswalker_enters_with_loyalty(self):
        pw_card = Card(
            name="Jace",
            card_type=CardType.PLANESWALKER,
            cost=ManaCost(generic=2, blue=1),
            loyalty=3,
            supertypes=[SuperType.LEGENDARY],
            activated_abilities=[
                {"loyalty_cost": 1, "is_loyalty": True, "effects": [{"type": "draw", "amount": 1}]},
            ],
        )
        game = Game(["Alice", "Bob"], [[pw_card], []])
        pw_inst = game.state.cards[0]

        # Move to battlefield via move_card (simulating resolution)
        game.state.move_card(pw_inst.instance_id, Zone.BATTLEFIELD)
        assert get_loyalty(pw_inst) == 3

    def test_planeswalker_zero_loyalty_sba(self):
        pw_card = Card(
            name="Jace",
            card_type=CardType.PLANESWALKER,
            cost=ManaCost(blue=1),
            loyalty=2,
            activated_abilities=[
                {"loyalty_cost": -2, "is_loyalty": True, "effects": [{"type": "draw", "amount": 1}]},
            ],
        )
        game = Game(["Alice", "Bob"], [[pw_card], []])
        pw_inst = game.state.cards[0]
        game.state.move_card(pw_inst.instance_id, Zone.BATTLEFIELD)

        # Activate -2 to reach 0 loyalty
        game.state.step = Step.MAIN
        result = activate_loyalty(pw_inst, 0, game.state.loyalty_activated_this_turn)
        assert result is not None
        assert get_loyalty(pw_inst) == 0

        # SBA should send it to graveyard
        actions = game.state.check_state_based_actions()
        assert pw_inst.zone == Zone.GRAVEYARD
        assert any("0 loyalty" in a for a in actions)

    def test_game_activate_planeswalker(self):
        pw_card = Card(
            name="Chandra",
            card_type=CardType.PLANESWALKER,
            cost=ManaCost(generic=2, red=2),
            loyalty=4,
            supertypes=[SuperType.LEGENDARY],
            activated_abilities=[
                {"loyalty_cost": 1, "is_loyalty": True,
                 "effects": [{"type": "damage", "amount": 2}]},
                {"loyalty_cost": -3, "is_loyalty": True,
                 "effects": [{"type": "damage", "amount": 4}]},
            ],
        )
        game = Game(["Alice", "Bob"], [[pw_card], []])
        pw_inst = game.state.cards[0]
        game.state.move_card(pw_inst.instance_id, Zone.BATTLEFIELD)
        game.state.step = Step.MAIN

        result = game.activate_planeswalker(0, pw_inst.instance_id, 0)
        assert result is True
        assert get_loyalty(pw_inst) == 5  # 4 + 1
        assert game.state.stack.size == 1
