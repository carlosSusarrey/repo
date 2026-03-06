"""Tests for extended effect resolution in game.py."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.game import Game
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost
from mtg_engine.core.stack import Stack, StackItem


def _simple_deck(n=20):
    return [
        Card(name=f"Bear {i}", card_type=CardType.CREATURE,
             cost=ManaCost.parse("{1}{G}"), power=2, toughness=2)
        for i in range(n)
    ]


def _setup_game():
    game = Game(["Alice", "Bob"], [_simple_deck(), _simple_deck()])
    game.draw_opening_hands()
    return game


class TestCounterEffect:
    def test_counter_spell_on_stack(self):
        game = _setup_game()

        # Create card instances for both spells
        bolt_card = Card(name="Lightning Bolt", card_type=CardType.INSTANT,
                         cost=ManaCost.parse("{R}"),
                         effects=[{"type": "damage", "target": {"kind": "target"}, "amount": 3}])
        bolt_instance = CardInstance(card=bolt_card, zone=Zone.STACK,
                                     instance_id="target_spell", owner_index=1, controller_index=1)
        game.state.cards.append(bolt_instance)

        target_item = StackItem(
            source_id="target_spell",
            controller_index=1,
            card_name="Lightning Bolt",
            effects=bolt_card.effects,
        )
        game.state.stack.push(target_item)

        counter_card = Card(name="Counterspell", card_type=CardType.INSTANT,
                            cost=ManaCost.parse("{U}{U}"),
                            effects=[{"type": "counter", "target": {"kind": "target", "target_type": "spell"}}])
        counter_instance = CardInstance(card=counter_card, zone=Zone.STACK,
                                        instance_id="counterspell", owner_index=0, controller_index=0)
        game.state.cards.append(counter_instance)

        counter_item = StackItem(
            source_id="counterspell",
            controller_index=0,
            card_name="Counterspell",
            effects=counter_card.effects,
            targets=["target_spell"],
        )
        game.state.stack.push(counter_item)

        result = game.resolve_top_of_stack()
        assert result is not None
        # The target spell should have been removed from stack
        assert game.state.stack.is_empty
        # Countered card goes to graveyard
        assert bolt_instance.zone == Zone.GRAVEYARD


class TestTapEffect:
    def test_tap_creature(self):
        game = _setup_game()
        # Put a creature on battlefield
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD
        assert not creature.tapped

        item = StackItem(
            source_id="icy",
            controller_index=0,
            card_name="Icy Manipulator",
            effects=[{"type": "tap", "target": {"kind": "target"}}],
            targets=[creature.instance_id],
        )
        result = game._resolve_effect({"type": "tap", "target": {"kind": "target"}}, item)
        assert result["success"]
        assert creature.tapped


class TestPumpEffect:
    def test_pump_target(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        item = StackItem(
            source_id="giant_growth",
            controller_index=0,
            card_name="Giant Growth",
            effects=[{"type": "pump", "target": {"kind": "target"}, "power": 3, "toughness": 3}],
            targets=[creature.instance_id],
        )
        result = game._resolve_effect(
            {"type": "pump", "target": {"kind": "target"}, "power": 3, "toughness": 3}, item
        )
        assert result["success"]
        assert creature.temp_power_mod == 3
        assert creature.temp_toughness_mod == 3

    def test_pump_self(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        item = StackItem(
            source_id=creature.instance_id,
            controller_index=0,
            card_name="Self Pumper",
            effects=[],
        )
        result = game._resolve_effect(
            {"type": "pump", "target": {"kind": "self"}, "power": 2, "toughness": 2}, item
        )
        assert result["success"]
        assert creature.temp_power_mod == 2


class TestAddCounterEffect:
    def test_add_counter_to_target(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        item = StackItem(
            source_id="spell",
            controller_index=0,
            card_name="Boon",
            effects=[],
            targets=[creature.instance_id],
        )
        result = game._resolve_effect(
            {"type": "add_counter", "target": {"kind": "target"}, "counter_type": "+1/+1", "amount": 2}, item
        )
        assert result["success"]
        assert creature.counters.get("+1/+1") == 2

    def test_add_counter_to_self(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        item = StackItem(
            source_id=creature.instance_id,
            controller_index=0,
            card_name="Self Counter",
            effects=[],
        )
        result = game._resolve_effect(
            {"type": "add_counter", "target": {"kind": "self"}, "counter_type": "+1/+1", "amount": 1}, item
        )
        assert result["success"]
        assert creature.counters.get("+1/+1") == 1


class TestMillEffect:
    def test_mill_cards(self):
        game = _setup_game()
        library_before = len(game.state.get_zone(0, Zone.LIBRARY))

        item = StackItem(
            source_id="mill_spell",
            controller_index=0,
            card_name="Tome Scour",
            effects=[],
        )
        result = game._resolve_effect({"type": "mill", "amount": 3}, item)
        assert result["success"]
        assert result["milled"] == 3


class TestExileEffect:
    def test_exile_creature(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        item = StackItem(
            source_id="exile_spell",
            controller_index=0,
            card_name="Swords to Plowshares",
            effects=[],
            targets=[creature.instance_id],
        )
        result = game._resolve_effect(
            {"type": "exile", "target": {"kind": "target"}}, item
        )
        assert result["success"]
        assert creature.zone == Zone.EXILE


class TestBounceEffect:
    def test_bounce_creature(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        item = StackItem(
            source_id="bounce_spell",
            controller_index=0,
            card_name="Unsummon",
            effects=[],
            targets=[creature.instance_id],
        )
        result = game._resolve_effect(
            {"type": "bounce", "target": {"kind": "target"}}, item
        )
        assert result["success"]
        assert creature.zone == Zone.HAND


class TestSacrificeEffect:
    def test_sacrifice_self(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        item = StackItem(
            source_id=creature.instance_id,
            controller_index=0,
            card_name="Selfless Spirit",
            effects=[],
        )
        result = game._resolve_effect(
            {"type": "sacrifice", "target": {"kind": "self"}}, item
        )
        assert result["success"]
        assert creature.zone == Zone.GRAVEYARD


class TestCreateTokenEffect:
    def test_create_token(self):
        game = _setup_game()
        item = StackItem(
            source_id="spell",
            controller_index=0,
            card_name="Raise the Alarm",
            effects=[],
        )
        result = game._resolve_effect(
            {"type": "create_token", "name": "Soldier", "power": 1, "toughness": 1}, item
        )
        assert result["success"]
        token_id = result["token_id"]
        token = game.state.find_card(token_id)
        assert token is not None
        assert token.is_token
        assert token.zone == Zone.BATTLEFIELD
        assert token.card.power == 1
        assert token.card.toughness == 1


class TestTokenCeaseToExist:
    def test_token_removed_when_leaving_battlefield(self):
        game = _setup_game()
        token = game.create_token(0, "Goblin", 1, 1)
        assert token in game.state.cards

        # Move token to graveyard
        token.zone = Zone.GRAVEYARD
        game.state.check_state_based_actions()

        # Token should be removed from game
        assert token not in game.state.cards


class TestAddManaEffect:
    def test_add_mana(self):
        game = _setup_game()
        item = StackItem(
            source_id="ritual",
            controller_index=0,
            card_name="Dark Ritual",
            effects=[],
        )
        player = game.state.players[0]
        before = player.mana_pool.black
        result = game._resolve_effect({"type": "add_mana", "color": "B"}, item)
        assert result["success"]
        assert player.mana_pool.black == before + 1


class TestAddKeywordEffect:
    def test_add_keyword_to_target(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        item = StackItem(
            source_id="spell",
            controller_index=0,
            card_name="Mighty Leap",
            effects=[],
            targets=[creature.instance_id],
        )
        result = game._resolve_effect(
            {"type": "add_keyword", "target": {"kind": "target"}, "keyword": "flying"}, item
        )
        assert result["success"]
        assert creature.has_keyword(Keyword.FLYING)


class TestStackRemoveBySource:
    def test_remove_by_source(self):
        stack = Stack()
        item1 = StackItem(source_id="a", controller_index=0, card_name="A")
        item2 = StackItem(source_id="b", controller_index=0, card_name="B")
        stack.push(item1)
        stack.push(item2)

        removed = stack.remove_by_source("a")
        assert removed is not None
        assert removed.source_id == "a"
        assert stack.size == 1

    def test_remove_nonexistent(self):
        stack = Stack()
        removed = stack.remove_by_source("missing")
        assert removed is None
