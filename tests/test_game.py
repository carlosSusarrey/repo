"""Tests for game state and game logic."""

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.game import Game
from mtg_engine.core.game_state import GameState
from mtg_engine.core.mana import ManaCost
from mtg_engine.core.player import Player


class TestGameState:
    def _make_state(self):
        state = GameState()
        state.players = [Player(name="Alice"), Player(name="Bob")]
        return state

    def test_initial_life(self):
        state = self._make_state()
        assert state.players[0].life == 20
        assert state.players[1].life == 20

    def test_state_based_actions_lethal_damage(self):
        state = self._make_state()
        card = Card(name="Bear", card_type=CardType.CREATURE, power=2, toughness=2)
        inst = CardInstance(card=card, zone=Zone.BATTLEFIELD, owner_index=0, controller_index=0)
        inst.damage_marked = 3
        state.cards.append(inst)

        actions = state.check_state_based_actions()
        assert len(actions) == 1
        assert "dies" in actions[0]
        assert inst.zone == Zone.GRAVEYARD

    def test_state_based_actions_life_loss(self):
        state = self._make_state()
        state.players[0].life = 0

        actions = state.check_state_based_actions()
        assert state.players[0].lost
        assert state.game_over


class TestGame:
    def _make_game(self):
        mountain = Card(name="Mountain", card_type=CardType.LAND)
        forest = Card(name="Forest", card_type=CardType.LAND)
        deck1 = [mountain] * 40
        deck2 = [forest] * 40
        return Game(["Alice", "Bob"], [deck1, deck2])

    def test_draw_opening_hands(self):
        game = self._make_game()
        game.draw_opening_hands()

        hand_a = game.state.get_zone(0, Zone.HAND)
        hand_b = game.state.get_zone(1, Zone.HAND)
        assert len(hand_a) == 7
        assert len(hand_b) == 7

    def test_play_land(self):
        game = self._make_game()
        game.draw_opening_hands()

        hand = game.state.get_zone(0, Zone.HAND)
        assert game.play_land(0, hand[0].instance_id)

        battlefield = game.state.get_battlefield(0)
        assert len(battlefield) == 1

    def test_cannot_play_two_lands(self):
        game = self._make_game()
        game.draw_opening_hands()

        hand = game.state.get_zone(0, Zone.HAND)
        assert game.play_land(0, hand[0].instance_id)
        assert not game.play_land(0, hand[1].instance_id)

    def test_draw_from_empty_library_loses(self):
        mountain = Card(name="Mountain", card_type=CardType.LAND)
        game = Game(["Alice", "Bob"], [[mountain] * 1, [mountain] * 40])
        game.draw_card(0)  # draws the only card
        game.draw_card(0)  # empty library
        assert game.state.players[0].lost
