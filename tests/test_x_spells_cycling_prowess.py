"""Tests for X spells, Phyrexian mana, cycling, and prowess."""

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Color, Step, Zone
from mtg_engine.core.game import Game
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import HybridMana, ManaCost, ManaPool, PhyrexianMana


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


# ---- X Spells ----

class TestXSpells:
    def _make_x_spell(self):
        """Blaze: {X}{R} — deal X damage to any target."""
        return Card(
            name="Blaze",
            card_type=CardType.SORCERY,
            cost=ManaCost.parse("{X}{R}"),
            effects=[{"type": "x_damage"}],
        )

    def test_x_spell_cost_has_x(self):
        """X spell's ManaCost correctly reports has_x."""
        spell = self._make_x_spell()
        assert spell.cost.has_x is True
        assert spell.cost.x_count == 1

    def test_cast_x_spell_with_x_value(self):
        """Cast an X spell with X=3, paying {3}{R} total."""
        spell = self._make_x_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 4)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Blaze")

        result = game.cast_spell(0, card.instance_id, targets=["Bob"], x_value=3)
        assert result is True
        assert card.zone == Zone.STACK
        assert card.x_value == 3
        # Should have spent 4 mana total (3 generic from X + 1 red)
        assert game.state.players[0].mana_pool.red == 0

    def test_cast_x_spell_x_equals_zero(self):
        """Cast X spell with X=0 — only pay base colored cost."""
        spell = self._make_x_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 1)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Blaze")

        result = game.cast_spell(0, card.instance_id, targets=["Bob"], x_value=0)
        assert result is True
        assert card.x_value == 0
        assert game.state.players[0].mana_pool.red == 0

    def test_x_spell_not_enough_mana(self):
        """Can't cast X spell if insufficient mana for chosen X."""
        spell = self._make_x_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 2)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Blaze")

        # X=3 needs {3}{R} = 4 mana, only have 2
        result = game.cast_spell(0, card.instance_id, targets=["Bob"], x_value=3)
        assert result is False
        assert card.zone == Zone.HAND

    def test_x_damage_resolution(self):
        """X damage effect deals X damage based on chosen x_value."""
        spell = self._make_x_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 5)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Blaze")

        game.cast_spell(0, card.instance_id, targets=["Bob"], x_value=4)
        bob_life_before = game.state.players[1].life
        game.resolve_top_of_stack()
        assert game.state.players[1].life == bob_life_before - 4

    def test_x_spell_x_value_cleared_after_resolution(self):
        """x_value is cleared after the spell resolves."""
        spell = self._make_x_spell()
        game = _make_game_with_cards([spell], [(Color.RED, 3)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Blaze")

        game.cast_spell(0, card.instance_id, targets=["Bob"], x_value=2)
        game.resolve_top_of_stack()
        assert card.x_value == 0

    def test_xx_spell(self):
        """Test spell with {X}{X}{R} cost (x_count=2)."""
        xx_spell = Card(
            name="XX Spell",
            card_type=CardType.SORCERY,
            cost=ManaCost.parse("{X}{X}{R}"),
            effects=[{"type": "x_damage"}],
        )
        assert xx_spell.cost.x_count == 2
        game = _make_game_with_cards([xx_spell], [(Color.RED, 5)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "XX Spell")

        # X=2 means {2}{2}{R} = 5 mana total
        result = game.cast_spell(0, card.instance_id, targets=["Bob"], x_value=2)
        assert result is True
        assert game.state.players[0].mana_pool.red == 0

    def test_mana_value_with_x(self):
        """ManaCost.mana_value_with_x returns correct value."""
        cost = ManaCost.parse("{X}{2}{R}")
        assert cost.converted_mana_cost == 3  # X=0 off stack
        assert cost.mana_value_with_x(5) == 8  # 5 + 2 + 1


# ---- Hybrid Mana ----

class TestHybridMana:
    def test_hybrid_mana_parse(self):
        """Hybrid mana parses correctly."""
        cost = ManaCost.parse("{W/U}{R}")
        assert len(cost.hybrid) == 1
        assert cost.hybrid[0].color1 == "W"
        assert cost.hybrid[0].color2 == "U"
        assert cost.red == 1

    def test_hybrid_mana_pay_with_first_color(self):
        """Hybrid mana can be paid with the first color option."""
        cost = ManaCost.parse("{W/U}")
        pool = ManaPool(white=1)
        assert pool.can_pay(cost)
        pool.pay(cost)
        assert pool.white == 0

    def test_hybrid_mana_pay_with_second_color(self):
        """Hybrid mana can be paid with the second color option."""
        cost = ManaCost.parse("{W/U}")
        pool = ManaPool(blue=1)
        assert pool.can_pay(cost)
        pool.pay(cost)
        assert pool.blue == 0

    def test_hybrid_mana_not_enough(self):
        """Can't pay hybrid mana without either color."""
        cost = ManaCost.parse("{W/U}")
        pool = ManaPool(red=1)
        assert not pool.can_pay(cost)

    def test_hybrid_mana_color_identity(self):
        """Hybrid mana contributes both colors to color identity."""
        cost = ManaCost.parse("{W/U}")
        assert Color.WHITE in cost.colors
        assert Color.BLUE in cost.colors

    def test_cast_hybrid_spell(self):
        """Cast a spell with hybrid mana cost using either color."""
        hybrid_card = Card(
            name="Hybrid Spell",
            card_type=CardType.INSTANT,
            cost=ManaCost.parse("{W/U}{R}"),
            effects=[{"type": "draw", "amount": 1}],
        )
        # Pay with white + red
        game = _make_game_with_cards([hybrid_card], [(Color.WHITE, 1), (Color.RED, 1)])
        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Hybrid Spell")
        result = game.cast_spell(0, card.instance_id)
        assert result is True


# ---- Phyrexian Mana ----

class TestPhyrexianMana:
    def test_phyrexian_mana_parse(self):
        """Phyrexian mana parses correctly."""
        cost = ManaCost.parse("{R/P}{G}")
        assert len(cost.phyrexian) == 1
        assert cost.phyrexian[0].color == "R"
        assert cost.green == 1

    def test_phyrexian_pay_with_mana(self):
        """Phyrexian mana can be paid with the appropriate color."""
        phyrexian_card = Card(
            name="Phyrexian Spell",
            card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R/P}"),
            effects=[{"type": "draw", "amount": 1}],
        )
        game = _make_game_with_cards([phyrexian_card], [(Color.RED, 1)])
        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Phyrexian Spell")

        # Pay with mana (no life payment)
        result = game.cast_spell(0, card.instance_id)
        assert result is True
        assert game.state.players[0].life == 20  # No life lost

    def test_phyrexian_pay_with_life(self):
        """Phyrexian mana can be paid with 2 life instead of mana."""
        phyrexian_card = Card(
            name="Phyrexian Spell",
            card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R/P}"),
            effects=[{"type": "draw", "amount": 1}],
        )
        game = _make_game_with_cards([phyrexian_card])
        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Phyrexian Spell")

        # Pay with life (index 0 = first phyrexian symbol)
        result = game.cast_spell(0, card.instance_id, phyrexian_life_pay=[0])
        assert result is True
        assert game.state.players[0].life == 18  # Lost 2 life

    def test_phyrexian_mixed_payment(self):
        """Pay some Phyrexian mana with life and some with mana."""
        # {R/P}{G/P} — two Phyrexian symbols
        card_def = Card(
            name="Double Phyrexian",
            card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R/P}{G/P}"),
            effects=[{"type": "draw", "amount": 1}],
        )
        # Only have red mana, pay green Phyrexian with life
        game = _make_game_with_cards([card_def], [(Color.RED, 1)])
        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Double Phyrexian")

        # Pay index 1 (the {G/P}) with life, index 0 ({R/P}) with red mana
        result = game.cast_spell(0, card.instance_id, phyrexian_life_pay=[1])
        assert result is True
        assert game.state.players[0].life == 18  # 2 life for {G/P}
        assert game.state.players[0].mana_pool.red == 0  # Paid {R/P} with mana

    def test_phyrexian_life_check(self):
        """Can't pay Phyrexian mana with life if it would kill you."""
        phyrexian_card = Card(
            name="Phyrexian Spell",
            card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R/P}"),
            effects=[{"type": "draw", "amount": 1}],
        )
        game = _make_game_with_cards([phyrexian_card])
        game.state.players[0].life = 2  # Exactly 2 — would die
        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Phyrexian Spell")

        result = game.cast_spell(0, card.instance_id, phyrexian_life_pay=[0])
        assert result is False  # Can't pay — would die

    def test_phyrexian_color_identity(self):
        """Phyrexian mana contributes its color to identity."""
        cost = ManaCost.parse("{R/P}")
        assert Color.RED in cost.colors


# ---- Cycling ----

class TestCycling:
    def _make_cycling_card(self):
        """A creature with cycling {2}."""
        return Card(
            name="Cycling Creature",
            card_type=CardType.CREATURE,
            cost=ManaCost.parse("{3}{G}"),
            power=4, toughness=4,
            cycling_cost="{2}",
        )

    def test_cycling_basic(self):
        """Cycling discards the card and draws a new one."""
        creature = self._make_cycling_card()
        game = _make_game_with_cards([creature], [(Color.RED, 2)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Cycling Creature")
        hand_size_before = len(hand)

        result = game.activate_cycling(0, card.instance_id)
        assert result is True
        assert card.zone == Zone.GRAVEYARD  # Discarded
        # Hand size: -1 (discard) + 1 (draw) = same
        assert len(game.state.get_zone(0, Zone.HAND)) == hand_size_before

    def test_cycling_pays_cost(self):
        """Cycling pays the cycling cost."""
        creature = self._make_cycling_card()
        game = _make_game_with_cards([creature], [(Color.RED, 3)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Cycling Creature")

        game.activate_cycling(0, card.instance_id)
        assert game.state.players[0].mana_pool.red == 1  # 3 - 2 = 1

    def test_cycling_fails_without_mana(self):
        """Can't cycle without enough mana."""
        creature = self._make_cycling_card()
        game = _make_game_with_cards([creature], [(Color.RED, 1)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Cycling Creature")

        result = game.activate_cycling(0, card.instance_id)
        assert result is False
        assert card.zone == Zone.HAND  # Still in hand

    def test_cycling_only_from_hand(self):
        """Can't cycle a card that's not in hand."""
        creature = self._make_cycling_card()
        game = _make_game_with_cards([creature], [(Color.RED, 2)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Cycling Creature")
        card.zone = Zone.GRAVEYARD

        result = game.activate_cycling(0, card.instance_id)
        assert result is False

    def test_no_cycling_cost(self):
        """Can't cycle a card without cycling ability."""
        normal_card = Card(
            name="Normal Creature",
            card_type=CardType.CREATURE,
            cost=ManaCost.parse("{G}"),
            power=1, toughness=1,
        )
        game = _make_game_with_cards([normal_card], [(Color.RED, 2)])

        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Normal Creature")

        result = game.activate_cycling(0, card.instance_id)
        assert result is False

    def test_cycling_with_colored_cost(self):
        """Cycling with a colored cost like {R}."""
        card_def = Card(
            name="Red Cycler",
            card_type=CardType.INSTANT,
            cost=ManaCost.parse("{3}{R}"),
            cycling_cost="{R}",
            effects=[{"type": "damage", "amount": 3}],
        )
        game = _make_game_with_cards([card_def], [(Color.RED, 1)])
        hand = game.state.get_zone(0, Zone.HAND)
        card = next(c for c in hand if c.name == "Red Cycler")

        result = game.activate_cycling(0, card.instance_id)
        assert result is True
        assert game.state.players[0].mana_pool.red == 0


# ---- Prowess ----

class TestProwess:
    def _make_prowess_creature(self):
        """A creature with prowess."""
        return Card(
            name="Monastery Swiftspear",
            card_type=CardType.CREATURE,
            cost=ManaCost.parse("{R}"),
            power=1, toughness=2,
            keywords={Keyword.PROWESS, Keyword.HASTE},
        )

    def _make_noncreature_spell(self):
        """A simple instant."""
        return Card(
            name="Lightning Bolt",
            card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R}"),
            effects=[{"type": "damage", "amount": 3}],
        )

    def test_prowess_triggers_on_noncreature(self):
        """Prowess triggers when a noncreature spell is cast."""
        creature = self._make_prowess_creature()
        spell = self._make_noncreature_spell()
        game = _make_game_with_cards([creature, spell], [(Color.RED, 5)])

        # Get creature onto battlefield
        hand = game.state.get_zone(0, Zone.HAND)
        cr = next(c for c in hand if c.name == "Monastery Swiftspear")
        game.cast_spell(0, cr.instance_id)
        game.resolve_top_of_stack()

        # Cast noncreature spell
        hand = game.state.get_zone(0, Zone.HAND)
        bolt = next(c for c in hand if c.name == "Lightning Bolt")
        game.cast_spell(0, bolt.instance_id, targets=["Bob"])

        # Prowess should have put a trigger on the stack
        # Stack: Lightning Bolt (bottom), prowess trigger (top)
        assert not game.state.stack.is_empty
        top = game.state.stack.peek()
        assert "prowess" in top.card_name.lower()

    def test_prowess_gives_plus_one(self):
        """Prowess trigger resolves to give +1/+1 until end of turn."""
        creature = self._make_prowess_creature()
        spell = self._make_noncreature_spell()
        game = _make_game_with_cards([creature, spell], [(Color.RED, 5)])

        hand = game.state.get_zone(0, Zone.HAND)
        cr = next(c for c in hand if c.name == "Monastery Swiftspear")
        game.cast_spell(0, cr.instance_id)
        game.resolve_top_of_stack()  # creature enters battlefield

        bf = game.state.get_battlefield(0)
        swiftspear = next(c for c in bf if c.name == "Monastery Swiftspear")
        assert swiftspear.current_power == 1
        assert swiftspear.current_toughness == 2

        hand = game.state.get_zone(0, Zone.HAND)
        bolt = next(c for c in hand if c.name == "Lightning Bolt")
        game.cast_spell(0, bolt.instance_id, targets=["Bob"])

        # Resolve prowess trigger (top of stack)
        game.resolve_top_of_stack()
        assert swiftspear.current_power == 2
        assert swiftspear.current_toughness == 3

    def test_prowess_does_not_trigger_on_creature(self):
        """Prowess does NOT trigger when a creature spell is cast."""
        creature = self._make_prowess_creature()
        bear = Card(
            name="Grizzly Bears",
            card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{G}"),
            power=2, toughness=2,
        )
        game = _make_game_with_cards([creature, bear], [(Color.RED, 1), (Color.GREEN, 2)])

        hand = game.state.get_zone(0, Zone.HAND)
        cr = next(c for c in hand if c.name == "Monastery Swiftspear")
        game.cast_spell(0, cr.instance_id)
        game.resolve_top_of_stack()

        stack_size_before = game.state.stack.size

        hand = game.state.get_zone(0, Zone.HAND)
        bear_card = next(c for c in hand if c.name == "Grizzly Bears")
        game.cast_spell(0, bear_card.instance_id)

        # Only the bear spell should be on the stack, no prowess trigger
        assert game.state.stack.size == stack_size_before + 1

    def test_multiple_prowess_creatures(self):
        """Multiple prowess creatures each trigger separately."""
        c1 = self._make_prowess_creature()
        c2 = Card(
            name="Soul-Scar Mage",
            card_type=CardType.CREATURE,
            cost=ManaCost.parse("{R}"),
            power=1, toughness=2,
            keywords={Keyword.PROWESS},
        )
        spell = self._make_noncreature_spell()
        game = _make_game_with_cards([c1, c2, spell], [(Color.RED, 6)])

        # Get both creatures on the battlefield
        hand = game.state.get_zone(0, Zone.HAND)
        for name in ["Monastery Swiftspear", "Soul-Scar Mage"]:
            card = next(c for c in hand if c.name == name)
            game.cast_spell(0, card.instance_id)
            game.resolve_top_of_stack()
            hand = game.state.get_zone(0, Zone.HAND)

        stack_before = game.state.stack.size
        hand = game.state.get_zone(0, Zone.HAND)
        bolt = next(c for c in hand if c.name == "Lightning Bolt")
        game.cast_spell(0, bolt.instance_id, targets=["Bob"])

        # Should have 2 prowess triggers + the spell = 3 total on stack
        # (prowess triggers are put on directly, not via pending triggers)
        prowess_count = 0
        for item in game.state.stack._items:
            if hasattr(item, 'card_name') and 'prowess' in item.card_name.lower():
                prowess_count += 1
        assert prowess_count == 2

    def test_prowess_clears_at_end_of_turn(self):
        """Prowess bonus clears at end of turn."""
        creature = self._make_prowess_creature()
        spell = self._make_noncreature_spell()
        game = _make_game_with_cards([creature, spell], [(Color.RED, 5)])

        hand = game.state.get_zone(0, Zone.HAND)
        cr = next(c for c in hand if c.name == "Monastery Swiftspear")
        game.cast_spell(0, cr.instance_id)
        game.resolve_top_of_stack()

        hand = game.state.get_zone(0, Zone.HAND)
        bolt = next(c for c in hand if c.name == "Lightning Bolt")
        game.cast_spell(0, bolt.instance_id, targets=["Bob"])
        game.resolve_top_of_stack()  # resolve prowess trigger

        bf = game.state.get_battlefield(0)
        swiftspear = next(c for c in bf if c.name == "Monastery Swiftspear")
        assert swiftspear.current_power == 2  # +1 from prowess

        # Clear end-of-turn effects
        swiftspear.clear_end_of_turn()
        assert swiftspear.current_power == 1  # Back to base
