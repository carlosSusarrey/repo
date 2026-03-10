"""Integration tests for sagas wired into the game engine.

Tests that:
- Sagas auto-setup on ETB with chapter 1 triggered
- Lore counters advance after draw step
- Completed sagas are sacrificed via SBA
- Chapter abilities go on the stack and resolve
"""

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.game import Game
from mtg_engine.core.game_state import GameState
from mtg_engine.core.mana import ManaCost
from mtg_engine.core.player import Player
from mtg_engine.core.sagas import is_saga, is_saga_complete, get_saga_chapter


def _make_state():
    state = GameState()
    state.players = [Player(name="Alice"), Player(name="Bob")]
    return state


def _make_saga_card(name="The Eldest Reborn", num_chapters=3):
    """Create a saga card with chapter abilities."""
    chapters = []
    for i in range(1, num_chapters + 1):
        chapters.append({
            "chapter": i,
            "effects": [{"type": "draw", "amount": 1}],
            "description": f"Chapter {i}",
        })
    return Card(
        name=name,
        card_type=CardType.ENCHANTMENT,
        cost=ManaCost.parse("{4}{B}"),
        subtypes=["Saga"],
        chapter_abilities=chapters,
    )


def _make_game():
    """Create a game with basic decks."""
    mountain = Card(name="Mountain", card_type=CardType.LAND)
    forest = Card(name="Forest", card_type=CardType.LAND)
    deck1 = [mountain] * 40
    deck2 = [forest] * 40
    return Game(["Alice", "Bob"], [deck1, deck2])


class TestSagaETB:
    def test_saga_setup_on_etb(self):
        """When a saga enters the battlefield, it is set up with lore counter = 1."""
        state = _make_state()
        saga = _make_saga_card()
        inst = CardInstance(card=saga, zone=Zone.HAND, owner_index=0, controller_index=0)
        state.cards.append(inst)

        state.move_card(inst.instance_id, Zone.BATTLEFIELD)

        assert is_saga(inst)
        assert inst.counters.get("lore") == 1
        assert inst.zone == Zone.BATTLEFIELD

    def test_chapter_1_triggers_on_etb(self):
        """Chapter 1 ability goes on the stack when saga enters."""
        state = _make_state()
        saga = _make_saga_card()
        inst = CardInstance(card=saga, zone=Zone.HAND, owner_index=0, controller_index=0)
        state.cards.append(inst)

        state.move_card(inst.instance_id, Zone.BATTLEFIELD)

        # Chapter 1 should be on the stack
        assert not state.stack.is_empty
        top = state.stack.peek()
        assert "chapter 1" in top.card_name.lower()

    def test_non_saga_enchantment_not_setup(self):
        """Non-saga enchantments should not get saga state."""
        state = _make_state()
        card = Card(
            name="Pacifism",
            card_type=CardType.ENCHANTMENT,
            subtypes=["Aura"],
        )
        inst = CardInstance(card=card, zone=Zone.HAND, owner_index=0, controller_index=0)
        state.cards.append(inst)

        state.move_card(inst.instance_id, Zone.BATTLEFIELD)

        assert not is_saga(inst)

    def test_saga_without_chapter_abilities_not_setup(self):
        """A saga subtype without chapter_abilities on the Card is not set up."""
        state = _make_state()
        card = Card(
            name="Empty Saga",
            card_type=CardType.ENCHANTMENT,
            subtypes=["Saga"],
            # No chapter_abilities defined
        )
        inst = CardInstance(card=card, zone=Zone.HAND, owner_index=0, controller_index=0)
        state.cards.append(inst)

        state.move_card(inst.instance_id, Zone.BATTLEFIELD)

        assert not is_saga(inst)


class TestSagaLoreAdvancement:
    def test_lore_counter_added_on_draw_step(self):
        """Saga gains a lore counter after the draw step."""
        game = _make_game()
        game.draw_opening_hands()

        saga = _make_saga_card(num_chapters=3)
        inst = CardInstance(
            card=saga, zone=Zone.HAND,
            owner_index=0, controller_index=0,
        )
        game.state.cards.append(inst)
        game.state.move_card(inst.instance_id, Zone.BATTLEFIELD)

        # Clear the stack (chapter 1 trigger)
        while not game.state.stack.is_empty:
            game.state.stack.pop()

        assert inst.counters["lore"] == 1

        # Simulate draw step advancing sagas
        game._advance_sagas(0)

        assert inst.counters["lore"] == 2

    def test_chapter_ability_on_stack_after_advance(self):
        """Chapter ability goes on the stack when lore counter is added."""
        game = _make_game()
        game.draw_opening_hands()

        saga = _make_saga_card(num_chapters=3)
        inst = CardInstance(
            card=saga, zone=Zone.HAND,
            owner_index=0, controller_index=0,
        )
        game.state.cards.append(inst)
        game.state.move_card(inst.instance_id, Zone.BATTLEFIELD)

        # Clear stack from chapter 1
        while not game.state.stack.is_empty:
            game.state.stack.pop()

        game._advance_sagas(0)

        assert not game.state.stack.is_empty
        top = game.state.stack.peek()
        assert "chapter 2" in top.card_name.lower()

    def test_opponent_sagas_not_advanced(self):
        """Only the active player's sagas advance."""
        game = _make_game()
        game.draw_opening_hands()

        saga = _make_saga_card()
        inst = CardInstance(
            card=saga, zone=Zone.HAND,
            owner_index=1, controller_index=1,
        )
        game.state.cards.append(inst)
        game.state.move_card(inst.instance_id, Zone.BATTLEFIELD)

        # Clear stack
        while not game.state.stack.is_empty:
            game.state.stack.pop()

        # Advance player 0's sagas — should not affect player 1's saga
        game._advance_sagas(0)
        assert inst.counters["lore"] == 1


class TestSagaSacrificeSBA:
    def test_completed_saga_sacrificed(self):
        """A saga at its final chapter is sacrificed by SBA."""
        state = _make_state()
        saga = _make_saga_card(num_chapters=2)
        inst = CardInstance(
            card=saga, zone=Zone.HAND,
            owner_index=0, controller_index=0,
        )
        state.cards.append(inst)
        state.move_card(inst.instance_id, Zone.BATTLEFIELD)

        # Manually set lore to final chapter
        inst.counters["lore"] = 2

        actions = state.check_state_based_actions()

        assert inst.zone == Zone.GRAVEYARD
        assert any("saga complete" in a for a in actions)

    def test_incomplete_saga_not_sacrificed(self):
        """A saga that hasn't reached its final chapter stays on the battlefield."""
        state = _make_state()
        saga = _make_saga_card(num_chapters=3)
        inst = CardInstance(
            card=saga, zone=Zone.HAND,
            owner_index=0, controller_index=0,
        )
        state.cards.append(inst)
        state.move_card(inst.instance_id, Zone.BATTLEFIELD)

        # Lore is 1 (from ETB), final is 3
        actions = state.check_state_based_actions()

        assert inst.zone == Zone.BATTLEFIELD
        assert not any("saga complete" in a for a in actions)


class TestSagaFullLifecycle:
    def test_three_chapter_saga_lifecycle(self):
        """A 3-chapter saga progresses through all chapters and is sacrificed."""
        game = _make_game()
        game.draw_opening_hands()

        saga = _make_saga_card(num_chapters=3)
        inst = CardInstance(
            card=saga, zone=Zone.HAND,
            owner_index=0, controller_index=0,
        )
        game.state.cards.append(inst)
        game.state.move_card(inst.instance_id, Zone.BATTLEFIELD)

        # Chapter 1 triggered on ETB, lore = 1
        assert inst.counters["lore"] == 1
        assert not game.state.stack.is_empty
        # Resolve chapter 1
        game.resolve_top_of_stack()

        # Draw step: lore -> 2, chapter 2 triggers
        game._advance_sagas(0)
        assert inst.counters["lore"] == 2
        assert not game.state.stack.is_empty
        game.resolve_top_of_stack()

        # Draw step: lore -> 3, chapter 3 triggers
        game._advance_sagas(0)
        assert inst.counters["lore"] == 3
        assert is_saga_complete(inst)
        # Chapter 3 is on the stack
        assert not game.state.stack.is_empty
        # Resolving chapter 3 triggers SBAs which sacrifice the saga
        game.resolve_top_of_stack()

        assert inst.zone == Zone.GRAVEYARD
