"""Tests for game state and game logic."""

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Color, Step, Zone
from mtg_engine.core.game import Game
from mtg_engine.core.game_state import GameState
from mtg_engine.core.mana import ManaCost
from mtg_engine.core.player import Player
from mtg_engine.core.triggers import TriggerEvent


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


class TestCastSpell:
    """Tests for casting spells and stack interaction."""

    def _make_game_with_spell(self, card_type=CardType.CREATURE, cost_str="{R}"):
        """Create a game where player 0 has a spell in hand and mana to cast it."""
        spell = Card(
            name="Test Spell",
            card_type=card_type,
            cost=ManaCost.parse(cost_str),
            power=2 if card_type == CardType.CREATURE else None,
            toughness=2 if card_type == CardType.CREATURE else None,
            effects=[{"type": "damage", "amount": 3}] if card_type in (CardType.INSTANT, CardType.SORCERY) else [],
        )
        mountain = Card(name="Mountain", card_type=CardType.LAND)
        deck1 = [spell] + [mountain] * 39
        deck2 = [mountain] * 40
        game = Game(["Alice", "Bob"], [deck1, deck2])
        game.draw_opening_hands()
        # Set to main phase so sorcery-speed spells can be cast
        game.state.step = Step.MAIN
        # Give player red mana
        game.state.players[0].mana_pool.add(Color.RED, 3)
        return game

    def test_cast_spell_puts_on_stack(self):
        """Casting a spell should move it to the stack zone and push a AbilityOnStack."""
        game = self._make_game_with_spell(CardType.CREATURE, "{R}")
        hand = game.state.get_zone(0, Zone.HAND)
        spell = next(c for c in hand if c.name == "Test Spell")

        assert game.state.stack.is_empty
        result = game.cast_spell(0, spell.instance_id)

        assert result is True
        assert spell.zone == Zone.STACK
        assert game.state.stack.size == 1
        assert game.state.stack.peek().card_name == "Test Spell"
        assert game.state.stack.peek().source_id == spell.instance_id

    def test_cast_spell_pays_mana(self):
        """Casting a spell should deduct mana from the player's pool."""
        game = self._make_game_with_spell(CardType.CREATURE, "{R}")
        hand = game.state.get_zone(0, Zone.HAND)
        spell = next(c for c in hand if c.name == "Test Spell")
        initial_red = game.state.players[0].mana_pool.red

        game.cast_spell(0, spell.instance_id)

        assert game.state.players[0].mana_pool.red == initial_red - 1

    def test_cast_spell_fails_without_mana(self):
        """Casting without sufficient mana should fail and leave card in hand."""
        game = self._make_game_with_spell(CardType.CREATURE, "{R}")
        game.state.players[0].mana_pool.empty()  # remove all mana
        hand = game.state.get_zone(0, Zone.HAND)
        spell = next(c for c in hand if c.name == "Test Spell")

        result = game.cast_spell(0, spell.instance_id)

        assert result is False
        assert spell.zone == Zone.HAND
        assert game.state.stack.is_empty

    def test_cast_land_fails(self):
        """Lands cannot be cast — they are played, not cast."""
        game = self._make_game_with_spell()
        hand = game.state.get_zone(0, Zone.HAND)
        land = next(c for c in hand if c.name == "Mountain")

        result = game.cast_spell(0, land.instance_id)

        assert result is False
        assert game.state.stack.is_empty

    def test_resolve_creature_goes_to_battlefield(self):
        """After resolving, a creature spell should move from stack to battlefield."""
        game = self._make_game_with_spell(CardType.CREATURE, "{R}")
        hand = game.state.get_zone(0, Zone.HAND)
        spell = next(c for c in hand if c.name == "Test Spell")

        game.cast_spell(0, spell.instance_id)
        assert spell.zone == Zone.STACK

        game.resolve_top_of_stack()
        assert spell.zone == Zone.BATTLEFIELD

    def test_resolve_instant_goes_to_graveyard(self):
        """After resolving, an instant should go to the graveyard."""
        game = self._make_game_with_spell(CardType.INSTANT, "{R}")
        hand = game.state.get_zone(0, Zone.HAND)
        spell = next(c for c in hand if c.name == "Test Spell")

        game.cast_spell(0, spell.instance_id)
        assert spell.zone == Zone.STACK

        game.resolve_top_of_stack()
        assert spell.zone == Zone.GRAVEYARD
        assert game.state.stack.is_empty

    def test_resolve_sorcery_goes_to_graveyard(self):
        """After resolving, a sorcery should go to the graveyard."""
        game = self._make_game_with_spell(CardType.SORCERY, "{R}")
        hand = game.state.get_zone(0, Zone.HAND)
        spell = next(c for c in hand if c.name == "Test Spell")

        game.cast_spell(0, spell.instance_id)
        game.resolve_top_of_stack()
        assert spell.zone == Zone.GRAVEYARD

    def test_multiple_spells_stack_lifo(self):
        """Multiple spells should resolve in LIFO order (last cast resolves first)."""
        spell_a = Card(name="Spell A", card_type=CardType.INSTANT,
                       cost=ManaCost.parse("{R}"), effects=[])
        spell_b = Card(name="Spell B", card_type=CardType.INSTANT,
                       cost=ManaCost.parse("{R}"), effects=[])
        mountain = Card(name="Mountain", card_type=CardType.LAND)
        deck1 = [spell_a, spell_b] + [mountain] * 38
        deck2 = [mountain] * 40
        game = Game(["Alice", "Bob"], [deck1, deck2])
        game.draw_opening_hands()
        game.state.step = Step.MAIN
        game.state.players[0].mana_pool.add(Color.RED, 5)

        hand = game.state.get_zone(0, Zone.HAND)
        card_a = next(c for c in hand if c.name == "Spell A")
        card_b = next(c for c in hand if c.name == "Spell B")

        game.cast_spell(0, card_a.instance_id)
        game.cast_spell(0, card_b.instance_id)

        assert game.state.stack.size == 2
        # LIFO: Spell B (cast second) should resolve first
        assert game.state.stack.peek().card_name == "Spell B"

        game.resolve_top_of_stack()
        assert game.state.stack.size == 1
        assert game.state.stack.peek().card_name == "Spell A"

    def test_cast_sorcery_fails_with_nonempty_stack(self):
        """Sorcery-speed spells can't be cast when the stack is non-empty."""
        spell_a = Card(name="Instant A", card_type=CardType.INSTANT,
                       cost=ManaCost.parse("{R}"), effects=[])
        spell_b = Card(name="Sorcery B", card_type=CardType.SORCERY,
                       cost=ManaCost.parse("{R}"), effects=[])
        mountain = Card(name="Mountain", card_type=CardType.LAND)
        deck1 = [spell_a, spell_b] + [mountain] * 38
        deck2 = [mountain] * 40
        game = Game(["Alice", "Bob"], [deck1, deck2])
        game.draw_opening_hands()
        game.state.step = Step.MAIN
        game.state.players[0].mana_pool.add(Color.RED, 5)

        hand = game.state.get_zone(0, Zone.HAND)
        instant = next(c for c in hand if c.name == "Instant A")
        sorcery = next(c for c in hand if c.name == "Sorcery B")

        # Cast instant first — stack is now non-empty
        game.cast_spell(0, instant.instance_id)
        assert game.state.stack.size == 1

        # Sorcery should fail because stack is non-empty
        result = game.cast_spell(0, sorcery.instance_id)
        assert result is False
        assert sorcery.zone == Zone.HAND


class TestFromZoneTracking:
    """Verify that ETB triggers carry from_zone so we can distinguish
    'was cast' (from_zone=STACK) vs 'put onto battlefield' (from_zone=HAND)."""

    def _make_game(self):
        mountain = Card(name="Mountain", card_type=CardType.LAND)
        deck = [mountain] * 40
        game = Game(["Alice", "Bob"], [deck, deck])
        game.draw_opening_hands()
        game.state.step = Step.MAIN
        return game

    def test_cast_creature_etb_from_zone_is_stack(self):
        """A creature cast from hand resolves through the stack.
        The ETB trigger event should carry from_zone=STACK.

        resolve_top_of_stack drains pending triggers onto the stack,
        so we check that the ETB ability ended up on the stack.
        To verify from_zone, we intercept the trigger before it's drained.
        """
        game = self._make_game()

        etb_watcher = Card(
            name="Watcher", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{G}"), power=1, toughness=1,
            triggered_abilities=[{
                "trigger": "enters_battlefield",
                "source": "self",
                "effects": [{"type": "gain_life", "amount": 1}],
            }],
        )
        inst = CardInstance(
            card=etb_watcher, zone=Zone.HAND,
            instance_id="watcher_1", owner_index=0, controller_index=0,
        )
        game.state.cards.append(inst)
        game.state.players[0].mana_pool.add(Color.GREEN, 1)

        game.cast_spell(0, inst.instance_id)
        assert inst.zone == Zone.STACK

        # Manually resolve the enter_battlefield effect so we can
        # inspect pending triggers before put_triggers_on_stack drains them
        item = game.state.stack.pop()
        for effect in item.effects:
            game._resolve_effect(effect, item)
        item.clear_stack_state()

        # Now the ETB trigger is in pending — check from_zone
        pending = game.state.triggers.pending
        etb_triggers = [
            p for p in pending
            if p.ability.trigger.event == TriggerEvent.ENTERS_BATTLEFIELD
        ]
        assert len(etb_triggers) == 1
        assert etb_triggers[0].event_data["from_zone"] == Zone.STACK

    def test_land_etb_from_zone_is_hand(self):
        """A land played from hand enters the battlefield directly.
        The ETB trigger event should carry from_zone=HAND."""
        game = self._make_game()

        etb_land = Card(
            name="ETB Land", card_type=CardType.LAND,
            triggered_abilities=[{
                "trigger": "enters_battlefield",
                "source": "self",
                "effects": [{"type": "gain_life", "amount": 1}],
            }],
        )
        inst = CardInstance(
            card=etb_land, zone=Zone.HAND,
            instance_id="etb_land_1", owner_index=0, controller_index=0,
        )
        game.state.cards.append(inst)

        game.play_land(0, inst.instance_id)
        assert inst.zone == Zone.BATTLEFIELD

        pending = game.state.triggers.pending
        etb_triggers = [
            p for p in pending
            if p.ability.trigger.event == TriggerEvent.ENTERS_BATTLEFIELD
        ]
        assert len(etb_triggers) == 1
        assert etb_triggers[0].event_data["from_zone"] == Zone.HAND

    def test_cast_vs_direct_placement_distinction(self):
        """The whole point: a creature cast from hand goes HAND→STACK→BATTLEFIELD
        (from_zone=STACK), while a land played directly goes HAND→BATTLEFIELD
        (from_zone=HAND). Triggers can tell the difference."""
        game = self._make_game()

        # --- Path 1: Cast creature from hand (goes through stack) ---
        creature_def = Card(
            name="Observer", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{G}"), power=1, toughness=1,
            triggered_abilities=[{
                "trigger": "enters_battlefield",
                "source": "self",
                "effects": [{"type": "gain_life", "amount": 1}],
            }],
        )
        cast_inst = CardInstance(
            card=creature_def, zone=Zone.HAND,
            instance_id="cast_obs", owner_index=0, controller_index=0,
        )
        game.state.cards.append(cast_inst)
        game.state.players[0].mana_pool.add(Color.GREEN, 1)

        game.cast_spell(0, cast_inst.instance_id)
        game.state.triggers.clear_pending()  # clear cast triggers

        # Manually resolve to inspect pending triggers before drain
        item = game.state.stack.pop()
        for effect in item.effects:
            game._resolve_effect(effect, item)
        item.clear_stack_state()

        cast_etbs = [
            p for p in game.state.triggers.pending
            if p.ability.trigger.event == TriggerEvent.ENTERS_BATTLEFIELD
        ]
        assert len(cast_etbs) == 1
        assert cast_etbs[0].event_data["from_zone"] == Zone.STACK
        game.state.triggers.clear_pending()

        # --- Path 2: Land played directly from hand (no stack) ---
        etb_land = Card(
            name="ETB Land", card_type=CardType.LAND,
            triggered_abilities=[{
                "trigger": "enters_battlefield",
                "source": "self",
                "effects": [{"type": "gain_life", "amount": 1}],
            }],
        )
        land_inst = CardInstance(
            card=etb_land, zone=Zone.HAND,
            instance_id="direct_land", owner_index=0, controller_index=0,
        )
        game.state.cards.append(land_inst)

        game.play_land(0, land_inst.instance_id)

        land_etbs = [
            p for p in game.state.triggers.pending
            if p.ability.trigger.event == TriggerEvent.ENTERS_BATTLEFIELD
        ]
        assert len(land_etbs) == 1
        assert land_etbs[0].event_data["from_zone"] == Zone.HAND

        # Both on battlefield, but their ETB events carried different from_zone
        assert cast_inst.zone == Zone.BATTLEFIELD
        assert land_inst.zone == Zone.BATTLEFIELD
