"""Tests for kicker and flashback mechanics."""

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Color, Step, Zone
from mtg_engine.core.game import Game
from mtg_engine.core.mana import ManaCost
from mtg_engine.core.player import Player


def _make_game_with_cards(cards_in_hand, extra_mana=None):
    """Create a game where player 0 has specific cards in hand with mana."""
    mountain = Card(name="Mountain", card_type=CardType.LAND)
    deck1 = list(cards_in_hand) + [mountain] * (40 - len(cards_in_hand))
    deck2 = [mountain] * 40
    game = Game(["Alice", "Bob"], [deck1, deck2])
    game.draw_opening_hands()
    game.state.step = Step.MAIN
    if extra_mana:
        for color, amount in extra_mana:
            game.state.players[0].mana_pool.add(color, amount)
    return game


class TestKicker:
    def _make_kicker_spell(self):
        """A sorcery that deals 2 damage, or 4 when kicked for {2}."""
        return Card(
            name="Burst Lightning",
            card_type=CardType.SORCERY,
            cost=ManaCost.parse("{R}"),
            effects=[{"type": "damage", "amount": 2}],
            kicker_cost="{2}",
            kicker_effects=[{"type": "damage", "amount": 2}],
        )

    def test_cast_without_kicker(self):
        """Cast a spell normally without paying kicker."""
        spell = self._make_kicker_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 3)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Burst Lightning")

        result = game.cast_spell(0, card.instance_id, targets=["Bob"])
        assert result is True
        assert card.zone == Zone.STACK
        assert card.was_kicked is False
        # Only base effect (1 damage effect)
        assert len(card.effects) == 1

    def test_cast_with_kicker(self):
        """Cast a spell with kicker — pays extra cost, gets extra effects."""
        spell = self._make_kicker_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 3)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Burst Lightning")

        result = game.cast_spell(0, card.instance_id, targets=["Bob"], kicked=True)
        assert result is True
        assert card.zone == Zone.STACK
        assert card.was_kicked is True
        # Base effect + kicker effect
        assert len(card.effects) == 2

    def test_kicker_pays_extra_mana(self):
        """Kicker costs additional mana on top of the base cost."""
        spell = self._make_kicker_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 3)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Burst Lightning")

        initial_red = game.state.players[0].mana_pool.red
        game.cast_spell(0, card.instance_id, targets=["Bob"], kicked=True)

        # {R} base + {2} kicker = 3 mana spent
        assert game.state.players[0].mana_pool.red == initial_red - 3

    def test_kicker_fails_without_enough_mana(self):
        """Can't kick if you can't afford base + kicker cost."""
        spell = self._make_kicker_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 1)])  # Only 1 mana

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Burst Lightning")

        # Can cast without kicker...
        # but let's try kicked — should fail
        result = game.cast_spell(0, card.instance_id, targets=["Bob"], kicked=True)
        assert result is False
        assert card.zone == Zone.HAND

    def test_kicker_without_kicker_cost_fails(self):
        """Can't kick a spell that doesn't have a kicker cost."""
        spell = Card(
            name="Lightning Bolt",
            card_type=CardType.SORCERY,
            cost=ManaCost.parse("{R}"),
            effects=[{"type": "damage", "amount": 3}],
        )
        game = _make_game_with_cards([spell], [(Color.RED, 5)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Lightning Bolt")

        result = game.cast_spell(0, card.instance_id, targets=["Bob"], kicked=True)
        assert result is False

    def test_kicker_creature(self):
        """Kicker works on creatures too — enters with bonus effect."""
        creature = Card(
            name="Gatekeeper of Malakir",
            card_type=CardType.CREATURE,
            cost=ManaCost.parse("{B}{B}"),
            power=2,
            toughness=2,
            kicker_cost="{B}",
            kicker_effects=[{"type": "sacrifice", "target_type": "creature"}],
        )
        game = _make_game_with_cards([creature], [(Color.BLACK, 5)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Gatekeeper of Malakir")

        result = game.cast_spell(0, card.instance_id, kicked=True)
        assert result is True
        assert card.was_kicked is True
        # enter_battlefield + kicker sacrifice effect
        assert any(e.get("type") == "sacrifice" for e in card.effects)

    def test_resolve_clears_kicked_state(self):
        """After resolution, was_kicked is cleared."""
        spell = self._make_kicker_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 3)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Burst Lightning")

        game.cast_spell(0, card.instance_id, targets=["Bob"], kicked=True)
        assert card.was_kicked is True

        game.resolve_top_of_stack()
        assert card.was_kicked is False


class TestFlashback:
    def _make_flashback_spell(self):
        """An instant with flashback — deals 3 damage."""
        return Card(
            name="Firebolt",
            card_type=CardType.SORCERY,
            cost=ManaCost.parse("{R}"),
            effects=[{"type": "damage", "amount": 3}],
            flashback_cost="{4}{R}",
        )

    def test_cast_from_graveyard(self):
        """Flashback allows casting from the graveyard."""
        spell = self._make_flashback_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 6)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Firebolt")

        # Move to graveyard first
        card.zone = Zone.GRAVEYARD

        result = game.cast_spell(0, card.instance_id, targets=["Bob"], flashback=True)
        assert result is True
        assert card.zone == Zone.STACK
        assert card.cast_with_flashback is True

    def test_flashback_uses_flashback_cost(self):
        """Flashback pays the flashback cost, not the regular cost."""
        spell = self._make_flashback_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 6)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Firebolt")
        card.zone = Zone.GRAVEYARD

        initial_red = game.state.players[0].mana_pool.red
        game.cast_spell(0, card.instance_id, targets=["Bob"], flashback=True)

        # {4}{R} = 5 total mana paid
        assert game.state.players[0].mana_pool.red == initial_red - 5

    def test_flashback_exiled_on_resolution(self):
        """Flashback spell goes to exile after resolution, not graveyard."""
        spell = self._make_flashback_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 6)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Firebolt")
        card.zone = Zone.GRAVEYARD

        game.cast_spell(0, card.instance_id, targets=["Bob"], flashback=True)
        game.resolve_top_of_stack()

        assert card.zone == Zone.EXILE

    def test_normal_cast_goes_to_graveyard(self):
        """Non-flashback cast of a flashback spell goes to graveyard as normal."""
        spell = self._make_flashback_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 3)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Firebolt")

        game.cast_spell(0, card.instance_id, targets=["Bob"])
        game.resolve_top_of_stack()

        assert card.zone == Zone.GRAVEYARD

    def test_flashback_from_hand_fails(self):
        """Can't flashback a spell that's in your hand."""
        spell = self._make_flashback_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 6)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Firebolt")

        result = game.cast_spell(0, card.instance_id, targets=["Bob"], flashback=True)
        assert result is False
        assert card.zone == Zone.HAND

    def test_flashback_without_flashback_cost_fails(self):
        """Can't flashback a spell without a flashback cost."""
        spell = Card(
            name="Lightning Bolt",
            card_type=CardType.SORCERY,
            cost=ManaCost.parse("{R}"),
            effects=[{"type": "damage", "amount": 3}],
        )
        game = _make_game_with_cards([spell], [(Color.RED, 5)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Lightning Bolt")
        card.zone = Zone.GRAVEYARD

        result = game.cast_spell(0, card.instance_id, targets=["Bob"], flashback=True)
        assert result is False

    def test_flashback_fails_without_enough_mana(self):
        """Can't flashback if you can't afford the flashback cost."""
        spell = self._make_flashback_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 2)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Firebolt")
        card.zone = Zone.GRAVEYARD

        result = game.cast_spell(0, card.instance_id, targets=["Bob"], flashback=True)
        assert result is False

    def test_flashback_clears_state_after_resolve(self):
        """After resolution, cast_with_flashback is cleared."""
        spell = self._make_flashback_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 6)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Firebolt")
        card.zone = Zone.GRAVEYARD

        game.cast_spell(0, card.instance_id, targets=["Bob"], flashback=True)
        assert card.cast_with_flashback is True

        game.resolve_top_of_stack()
        assert card.cast_with_flashback is False

    def test_flashback_with_kicker(self):
        """A spell can be both flashed back and kicked."""
        spell = Card(
            name="Fight with Fire",
            card_type=CardType.SORCERY,
            cost=ManaCost.parse("{2}{R}"),
            effects=[{"type": "damage", "amount": 5}],
            kicker_cost="{5}{R}",
            kicker_effects=[{"type": "damage", "amount": 5}],
            flashback_cost="{5}{R}{R}",
        )
        game = _make_game_with_cards([spell], [(Color.RED, 20)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Fight with Fire")
        card.zone = Zone.GRAVEYARD

        result = game.cast_spell(
            0, card.instance_id, targets=["Bob"],
            kicked=True, flashback=True,
        )
        assert result is True
        assert card.was_kicked is True
        assert card.cast_with_flashback is True
        assert len(card.effects) == 2  # base + kicker

        game.resolve_top_of_stack()
        assert card.zone == Zone.EXILE  # flashback exiles
