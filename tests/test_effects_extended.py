"""Tests for extended effect resolution in game.py.

All tests cast spells through the stack to verify the full
cast → stack → resolve pipeline, not just _resolve_effect in isolation.
"""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Color, Step, Zone
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


def _cast_and_resolve(game, card, effects, targets=None, controller=0):
    """Put a spell card on the stack and resolve it, returning the result.

    Creates a CardInstance for the card, puts it in the STACK zone,
    pushes a StackItem with the given effects, then resolves via
    resolve_top_of_stack().
    """
    instance = CardInstance(
        card=card, zone=Zone.STACK,
        instance_id=card.name.lower().replace(" ", "_"),
        owner_index=controller, controller_index=controller,
    )
    game.state.cards.append(instance)

    item = StackItem(
        source_id=instance.instance_id,
        controller_index=controller,
        card_name=card.name,
        effects=effects,
        targets=targets or [],
    )
    game.state.stack.push(item)
    return game.resolve_top_of_stack()


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
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD
        assert not creature.tapped

        tap_spell = Card(name="Icy Manipulator", card_type=CardType.INSTANT,
                         effects=[{"type": "tap", "target": {"kind": "target"}}])
        result = _cast_and_resolve(
            game, tap_spell,
            effects=[{"type": "tap", "target": {"kind": "target"}}],
            targets=[creature.instance_id],
        )
        assert result is not None
        assert any(e["success"] for e in result["effects_resolved"])
        assert creature.tapped


class TestPumpEffect:
    def test_pump_target(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        pump_effect = {"type": "pump", "target": {"kind": "target"}, "power": 3, "toughness": 3}
        pump_spell = Card(name="Giant Growth", card_type=CardType.INSTANT, effects=[pump_effect])
        result = _cast_and_resolve(
            game, pump_spell,
            effects=[pump_effect],
            targets=[creature.instance_id],
        )
        assert any(e["success"] for e in result["effects_resolved"])
        assert creature.temp_power_mod == 3
        assert creature.temp_toughness_mod == 3

    def test_pump_self(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        pump_effect = {"type": "pump", "target": {"kind": "self"}, "power": 2, "toughness": 2}
        # Source is the creature itself (activated ability style)
        item = StackItem(
            source_id=creature.instance_id,
            controller_index=0,
            card_name="Self Pumper",
            effects=[pump_effect],
        )
        game.state.stack.push(item)
        # resolve_top_of_stack won't iterate effects for creatures unless
        # they're instant/sorcery, so we test _resolve_effect directly here
        # since self-pump is typically an activated ability, not a spell
        result = game._resolve_effect(pump_effect, item)
        assert result["success"]
        assert creature.temp_power_mod == 2


class TestAddCounterEffect:
    def test_add_counter_to_target(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        counter_effect = {"type": "add_counter", "target": {"kind": "target"}, "counter_type": "+1/+1", "amount": 2}
        spell = Card(name="Boon", card_type=CardType.SORCERY, effects=[counter_effect])
        result = _cast_and_resolve(
            game, spell,
            effects=[counter_effect],
            targets=[creature.instance_id],
        )
        assert any(e["success"] for e in result["effects_resolved"])
        assert creature.counters.get("+1/+1") == 2

    def test_add_counter_to_self(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        counter_effect = {"type": "add_counter", "target": {"kind": "self"}, "counter_type": "+1/+1", "amount": 1}
        # Self-targeting is an activated ability — test via _resolve_effect
        item = StackItem(
            source_id=creature.instance_id,
            controller_index=0,
            card_name="Self Counter",
            effects=[counter_effect],
        )
        result = game._resolve_effect(counter_effect, item)
        assert result["success"]
        assert creature.counters.get("+1/+1") == 1


class TestMillEffect:
    def test_mill_cards(self):
        game = _setup_game()
        library_before = len(game.state.get_zone(0, Zone.LIBRARY))

        mill_effect = {"type": "mill", "amount": 3}
        spell = Card(name="Tome Scour", card_type=CardType.SORCERY, effects=[mill_effect])
        result = _cast_and_resolve(game, spell, effects=[mill_effect])
        assert any(e["success"] for e in result["effects_resolved"])
        assert any(e.get("milled") == 3 for e in result["effects_resolved"])


class TestExileEffect:
    def test_exile_creature(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        exile_effect = {"type": "exile", "target": {"kind": "target"}}
        spell = Card(name="Swords to Plowshares", card_type=CardType.INSTANT, effects=[exile_effect])
        result = _cast_and_resolve(
            game, spell,
            effects=[exile_effect],
            targets=[creature.instance_id],
        )
        assert any(e["success"] for e in result["effects_resolved"])
        assert creature.zone == Zone.EXILE


class TestBounceEffect:
    def test_bounce_creature(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        bounce_effect = {"type": "bounce", "target": {"kind": "target"}}
        spell = Card(name="Unsummon", card_type=CardType.INSTANT, effects=[bounce_effect])
        result = _cast_and_resolve(
            game, spell,
            effects=[bounce_effect],
            targets=[creature.instance_id],
        )
        assert any(e["success"] for e in result["effects_resolved"])
        assert creature.zone == Zone.HAND


class TestSacrificeEffect:
    def test_sacrifice_self(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        sac_effect = {"type": "sacrifice", "target": {"kind": "self"}}
        # Sacrifice self is an activated ability — test via _resolve_effect
        item = StackItem(
            source_id=creature.instance_id,
            controller_index=0,
            card_name="Selfless Spirit",
            effects=[sac_effect],
        )
        result = game._resolve_effect(sac_effect, item)
        assert result["success"]
        assert creature.zone == Zone.GRAVEYARD


class TestCreateTokenEffect:
    def test_create_token(self):
        game = _setup_game()
        token_effect = {"type": "create_token", "name": "Soldier", "power": 1, "toughness": 1}
        spell = Card(name="Raise the Alarm", card_type=CardType.INSTANT, effects=[token_effect])
        result = _cast_and_resolve(game, spell, effects=[token_effect])
        assert any(e["success"] for e in result["effects_resolved"])
        token_id = next(e["token_id"] for e in result["effects_resolved"] if e.get("token_id"))
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
        mana_effect = {"type": "add_mana", "color": "B"}
        spell = Card(name="Dark Ritual", card_type=CardType.INSTANT, effects=[mana_effect])
        player = game.state.players[0]
        before = player.mana_pool.black
        result = _cast_and_resolve(game, spell, effects=[mana_effect])
        assert any(e["success"] for e in result["effects_resolved"])
        assert player.mana_pool.black == before + 1


class TestAddKeywordEffect:
    def test_add_keyword_to_target(self):
        game = _setup_game()
        creature = game.state.cards[0]
        creature.zone = Zone.BATTLEFIELD

        keyword_effect = {"type": "add_keyword", "target": {"kind": "target"}, "keyword": "flying"}
        spell = Card(name="Mighty Leap", card_type=CardType.INSTANT, effects=[keyword_effect])
        result = _cast_and_resolve(
            game, spell,
            effects=[keyword_effect],
            targets=[creature.instance_id],
        )
        assert any(e["success"] for e in result["effects_resolved"])
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
