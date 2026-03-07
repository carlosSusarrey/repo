"""Integration tests for replacement effects wired into the game engine.

These tests verify that the ReplacementEffectManager is correctly consulted
during actual game actions: damage, life gain, draw, ETB, and death.
"""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.game import Game
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost
from mtg_engine.core.replacement_effects import (
    ReplacementEffect,
    ReplacementEffectManager,
    ReplacementType,
    create_prevention_effect,
    create_etb_with_counters,
    create_etb_tapped,
    create_damage_redirect,
    create_life_gain_replacement,
    create_draw_replacement,
)
from mtg_engine.core.stack import AbilityOnStack
from mtg_engine.core.triggers import TriggerEvent


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


def _place_on_battlefield(game, card, controller=0, instance_id=None):
    inst = CardInstance(
        card=card, zone=Zone.BATTLEFIELD,
        instance_id=instance_id or card.name.lower().replace(" ", "_"),
        owner_index=controller, controller_index=controller,
    )
    game.state.cards.append(inst)
    return inst


# ─── ETB Replacement: Enters Tapped ──────────────────────────────────────


class TestETBEntersTapped:
    """Cards that enter the battlefield tapped (e.g., taplands)."""

    def test_etb_tapped_via_card_data(self):
        """A card with a replacement effect enters tapped."""
        game = _setup_game()

        tapland = Card(
            name="Tapland", card_type=CardType.LAND,
            replacement_effects=[{
                "type": "enter_battlefield",
                "action": "enter_tapped",
                "apply_to": "self",
            }],
        )
        inst = CardInstance(
            card=tapland, zone=Zone.HAND,
            instance_id="tapland_1", owner_index=0, controller_index=0,
        )
        game.state.cards.append(inst)

        # Move to battlefield triggers replacement registration + ETB check
        game.state.move_card("tapland_1", Zone.BATTLEFIELD)

        assert inst.zone == Zone.BATTLEFIELD
        assert inst.tapped is True

    def test_etb_tapped_via_manager_directly(self):
        """Register an enter-tapped effect directly, then move card."""
        game = _setup_game()

        land = Card(name="Slow Land", card_type=CardType.LAND)
        inst = CardInstance(
            card=land, zone=Zone.HAND,
            instance_id="slow_land", owner_index=0, controller_index=0,
        )
        game.state.cards.append(inst)

        # Pre-register effect (simulating an external source)
        effect = create_etb_tapped("slow_land")
        game.state.replacement_effects.add_effect(effect)

        game.state.move_card("slow_land", Zone.BATTLEFIELD)
        assert inst.tapped is True

    def test_normal_land_not_tapped(self):
        """Without replacement, land enters untapped."""
        game = _setup_game()

        land = Card(name="Fast Land", card_type=CardType.LAND)
        inst = CardInstance(
            card=land, zone=Zone.HAND,
            instance_id="fast_land", owner_index=0, controller_index=0,
        )
        game.state.cards.append(inst)

        game.state.move_card("fast_land", Zone.BATTLEFIELD)
        assert inst.tapped is False


# ─── ETB Replacement: Enters With Counters ────────────────────────────────


class TestETBWithCounters:
    """Cards that enter with counters (e.g., Hydras, Walking Ballista)."""

    def test_etb_with_counters_via_card_data(self):
        """A creature enters with +1/+1 counters from card data."""
        game = _setup_game()

        hydra = Card(
            name="Baby Hydra", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{2}{G}"), power=0, toughness=0,
            replacement_effects=[{
                "type": "enter_battlefield",
                "action": "add_counters",
                "counter_type": "+1/+1",
                "count": 3,
                "apply_to": "self",
            }],
        )
        inst = CardInstance(
            card=hydra, zone=Zone.HAND,
            instance_id="hydra_1", owner_index=0, controller_index=0,
        )
        game.state.cards.append(inst)

        game.state.move_card("hydra_1", Zone.BATTLEFIELD)

        assert inst.zone == Zone.BATTLEFIELD
        assert inst.counters.get("+1/+1") == 3
        assert inst.current_power == 3  # 0 base + 3 counters
        assert inst.current_toughness == 3

    def test_etb_with_counters_via_manager(self):
        """Register counter effect directly, then move card."""
        game = _setup_game()

        creature = Card(
            name="Counter Guy", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{G}"), power=1, toughness=1,
        )
        inst = CardInstance(
            card=creature, zone=Zone.HAND,
            instance_id="counter_guy", owner_index=0, controller_index=0,
        )
        game.state.cards.append(inst)

        effect = create_etb_with_counters("counter_guy", "+1/+1", 2)
        game.state.replacement_effects.add_effect(effect)

        game.state.move_card("counter_guy", Zone.BATTLEFIELD)

        assert inst.counters.get("+1/+1") == 2
        assert inst.current_power == 3  # 1 base + 2 counters


# ─── Damage Prevention ────────────────────────────────────────────────────


class TestDamagePrevention:
    """Damage replacement effects preventing or reducing damage."""

    def test_prevent_all_damage_to_player(self):
        """Full damage prevention prevents damage to player."""
        game = _setup_game()
        alice = game.state.players[0]
        initial_life = alice.life

        effect = create_prevention_effect("shield_src")
        game.state.replacement_effects.add_effect(effect)

        # Resolve a damage spell targeting Alice
        bolt = Card(name="Lightning Bolt", card_type=CardType.INSTANT,
                    cost=ManaCost.parse("{R}"),
                    effects=[{"type": "damage", "amount": 3}])
        bolt_inst = CardInstance(
            card=bolt, zone=Zone.STACK,
            instance_id="bolt1", owner_index=1, controller_index=1,
        )
        game.state.cards.append(bolt_inst)

        item = AbilityOnStack(
            source_id="bolt1", controller_index=1,
            card_name="Lightning Bolt",
            effects=[{"type": "damage", "amount": 3}],
            targets=["Alice"],
        )
        game.state.stack.push(item)
        game.resolve_top_of_stack()

        assert alice.life == initial_life  # No damage dealt

    def test_partial_damage_prevention(self):
        """Prevent 2 of 5 damage to player."""
        game = _setup_game()
        alice = game.state.players[0]
        initial_life = alice.life

        effect = create_prevention_effect("shield", prevent_amount=2)
        game.state.replacement_effects.add_effect(effect)

        item = AbilityOnStack(
            source_id="src", controller_index=1,
            card_name="Fireball",
            effects=[{"type": "damage", "amount": 5}],
            targets=["Alice"],
        )
        game.state.stack.push(item)
        game.resolve_top_of_stack()

        assert alice.life == initial_life - 3  # 5 - 2 prevented = 3

    def test_prevent_damage_to_creature(self):
        """Damage prevention applies to creature damage too."""
        game = _setup_game()

        bear_card = Card(name="Bear", card_type=CardType.CREATURE,
                         cost=ManaCost.parse("{1}{G}"), power=2, toughness=2)
        bear = _place_on_battlefield(game, bear_card, controller=0, instance_id="bear")

        effect = create_prevention_effect("shield")
        game.state.replacement_effects.add_effect(effect)

        item = AbilityOnStack(
            source_id="src", controller_index=1,
            card_name="Shock",
            effects=[{"type": "damage", "amount": 2}],
            targets=["bear"],
        )
        game.state.stack.push(item)
        game.resolve_top_of_stack()

        assert bear.damage_marked == 0  # All damage prevented


# ─── Life Gain Replacement ────────────────────────────────────────────────


class TestLifeGainReplacement:
    """Replacement effects modifying life gain."""

    def test_double_life_gain(self):
        """Life gain doubler (Trostani, etc.) doubles gain amount."""
        game = _setup_game()
        alice = game.state.players[0]
        initial_life = alice.life

        effect = create_life_gain_replacement(
            "doubler",
            apply_fn=lambda e: {**e, "amount": e.get("amount", 0) * 2},
        )
        game.state.replacement_effects.add_effect(effect)

        item = AbilityOnStack(
            source_id="src", controller_index=0,
            card_name="Healing Salve",
            effects=[{"type": "gain_life", "amount": 3}],
        )
        game.state.stack.push(item)
        game.resolve_top_of_stack()

        assert alice.life == initial_life + 6  # 3 * 2 = 6

    def test_prevent_life_gain(self):
        """Tainted Remedy style: prevent life gain entirely."""
        game = _setup_game()
        alice = game.state.players[0]
        initial_life = alice.life

        effect = create_life_gain_replacement(
            "tainted",
            apply_fn=lambda e: None,
        )
        game.state.replacement_effects.add_effect(effect)

        item = AbilityOnStack(
            source_id="src", controller_index=0,
            card_name="Healing Salve",
            effects=[{"type": "gain_life", "amount": 5}],
        )
        game.state.stack.push(item)
        game.resolve_top_of_stack()

        assert alice.life == initial_life  # No life gained

    def test_double_life_via_card_data(self):
        """A card with 'double_life' replacement effect declared in card data."""
        game = _setup_game()
        alice = game.state.players[0]
        initial_life = alice.life

        doubler = Card(
            name="Life Doubler", card_type=CardType.ENCHANTMENT,
            cost=ManaCost.parse("{2}{W}"),
            replacement_effects=[{
                "type": "life_gain",
                "action": "double_life",
                "apply_to": "any",
            }],
        )
        _place_on_battlefield(game, doubler, controller=0, instance_id="doubler")
        # Registration happens during move_card — but we placed directly.
        # So manually register.
        game.state._register_replacement_effects(game.state.find_card("doubler"))

        item = AbilityOnStack(
            source_id="src", controller_index=0,
            card_name="Healing Salve",
            effects=[{"type": "gain_life", "amount": 4}],
        )
        game.state.stack.push(item)
        game.resolve_top_of_stack()

        assert alice.life == initial_life + 8  # 4 * 2


# ─── Draw Replacement ─────────────────────────────────────────────────────


class TestDrawReplacement:
    """Replacement effects modifying draws."""

    def test_prevent_draw(self):
        """Prevent a draw entirely (Notion Thief style)."""
        game = _setup_game()
        hand_before = len(game.state.get_zone(0, Zone.HAND))

        effect = create_draw_replacement(
            "blocker",
            apply_fn=lambda e: None,
        )
        game.state.replacement_effects.add_effect(effect)

        card = game.draw_card(0)
        assert card is None
        assert len(game.state.get_zone(0, Zone.HAND)) == hand_before

    def test_draw_without_replacement(self):
        """Normal draw works when no replacement effect exists."""
        game = _setup_game()
        hand_before = len(game.state.get_zone(0, Zone.HAND))

        card = game.draw_card(0)
        assert card is not None
        assert len(game.state.get_zone(0, Zone.HAND)) == hand_before + 1


# ─── Death Replacement ────────────────────────────────────────────────────


class TestDeathReplacement:
    """Replacement effects that prevent or modify dying."""

    def test_prevent_death_from_destroy(self):
        """A creature with 'if would die, prevent' survives destroy."""
        game = _setup_game()

        angel = Card(
            name="Resilient Angel", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{3}{W}"), power=4, toughness=4,
        )
        angel_inst = _place_on_battlefield(game, angel, controller=0, instance_id="angel")

        # Register a die-prevention effect for this creature
        effect = ReplacementEffect(
            source_id="angel",
            replacement_type=ReplacementType.DIE,
            prevent=True,
            condition=lambda e: e.get("card_id") == "angel",
            is_self_replacement=True,
        )
        game.state.replacement_effects.add_effect(effect)

        # Cast destroy spell
        destroy = Card(name="Murder", card_type=CardType.INSTANT,
                       cost=ManaCost.parse("{1}{B}{B}"),
                       effects=[{"type": "destroy"}])
        destroy_inst = CardInstance(
            card=destroy, zone=Zone.STACK,
            instance_id="murder1", owner_index=1, controller_index=1,
        )
        game.state.cards.append(destroy_inst)

        item = AbilityOnStack(
            source_id="murder1", controller_index=1,
            card_name="Murder",
            effects=[{"type": "destroy"}],
            targets=["angel"],
        )
        game.state.stack.push(item)
        game.resolve_top_of_stack()

        # Angel should still be on the battlefield
        assert angel_inst.zone == Zone.BATTLEFIELD

    def test_prevent_death_from_lethal_damage_sba(self):
        """Death replacement prevents SBA-based creature death from lethal damage."""
        game = _setup_game()

        tough = Card(
            name="Tough Guy", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{G}"), power=1, toughness=2,
        )
        inst = _place_on_battlefield(game, tough, controller=0, instance_id="tough")
        inst.damage_marked = 5  # Lethal damage

        # Register die prevention
        effect = ReplacementEffect(
            source_id="tough",
            replacement_type=ReplacementType.DIE,
            prevent=True,
            condition=lambda e: e.get("card_id") == "tough",
            is_self_replacement=True,
        )
        game.state.replacement_effects.add_effect(effect)

        actions = game.state.check_state_based_actions()

        # Should still be on battlefield, damage reset
        assert inst.zone == Zone.BATTLEFIELD
        assert inst.damage_marked == 0
        assert any("death prevented" in a for a in actions)

    def test_prevent_death_via_card_data(self):
        """A card with die-prevent replacement declared in card data."""
        game = _setup_game()

        undying = Card(
            name="Undying Phoenix", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{3}{R}"), power=3, toughness=3,
            replacement_effects=[{
                "type": "die",
                "action": "prevent",
                "apply_to": "self",
            }],
        )
        inst = CardInstance(
            card=undying, zone=Zone.HAND,
            instance_id="phoenix", owner_index=0, controller_index=0,
        )
        game.state.cards.append(inst)

        # Move to battlefield (registers replacement effects)
        game.state.move_card("phoenix", Zone.BATTLEFIELD)

        # Mark lethal damage
        inst.damage_marked = 5

        actions = game.state.check_state_based_actions()

        assert inst.zone == Zone.BATTLEFIELD
        assert inst.damage_marked == 0


# ─── Damage Redirect ──────────────────────────────────────────────────────


class TestDamageRedirect:
    """Damage redirection replacement effects."""

    def test_redirect_damage_to_creature(self):
        """Redirect player damage to a creature."""
        game = _setup_game()
        alice = game.state.players[0]
        initial_life = alice.life

        bear = Card(name="Bear", card_type=CardType.CREATURE,
                    cost=ManaCost.parse("{1}{G}"), power=2, toughness=4)
        bear_inst = _place_on_battlefield(game, bear, controller=0, instance_id="shield_bear")

        effect = create_damage_redirect("src", "shield_bear",
                                        condition=lambda e: e.get("target") == "Alice")
        game.state.replacement_effects.add_effect(effect)

        item = AbilityOnStack(
            source_id="src", controller_index=1,
            card_name="Bolt",
            effects=[{"type": "damage", "amount": 3}],
            targets=["Alice"],
        )
        game.state.stack.push(item)
        game.resolve_top_of_stack()

        assert alice.life == initial_life  # No damage to player
        assert bear_inst.damage_marked == 3  # Damage redirected to creature


# ─── Replacement Cleanup On Leave ─────────────────────────────────────────


class TestReplacementCleanup:
    """Replacement effects are removed when their source leaves battlefield."""

    def test_effects_removed_on_leave(self):
        """When a permanent with replacement effects leaves, its effects are cleared."""
        game = _setup_game()

        enchant = Card(
            name="Damage Shield", card_type=CardType.ENCHANTMENT,
            cost=ManaCost.parse("{1}{W}"),
            replacement_effects=[{
                "type": "damage",
                "action": "prevent_damage",
                "apply_to": "any",
            }],
        )
        inst = CardInstance(
            card=enchant, zone=Zone.HAND,
            instance_id="shield1", owner_index=0, controller_index=0,
        )
        game.state.cards.append(inst)

        # Enter battlefield — registers replacement effects
        game.state.move_card("shield1", Zone.BATTLEFIELD)
        assert len(game.state.replacement_effects.effects) > 0

        # Leave battlefield — replacement effects should be cleared
        game.state.move_card("shield1", Zone.GRAVEYARD)
        effects_from_shield = [
            e for e in game.state.replacement_effects.effects
            if e.source_id == "shield1"
        ]
        assert len(effects_from_shield) == 0


# ─── DSL Parsing ──────────────────────────────────────────────────────────


class TestDSLReplacementEffects:
    """Test DSL grammar parsing for replacement effects."""

    def test_parse_enter_tapped(self):
        from mtg_engine.dsl.parser import parse_card
        cards = parse_card('''
            card "Tapland" {
                type: Land
                replace(enter_battlefield): enter_tapped
            }
        ''')
        card = cards[0]
        assert len(card.replacement_effects) == 1
        repl = card.replacement_effects[0]
        assert repl["type"] == "enter_battlefield"
        assert repl["action"] == "enter_tapped"
        assert repl["apply_to"] == "self"

    def test_parse_add_counters(self):
        from mtg_engine.dsl.parser import parse_card
        cards = parse_card('''
            card "Hydra" {
                type: Creature
                cost: {X}{G}
                p/t: 0 / 0
                replace(enter_battlefield): add_counters("+1/+1", 3)
            }
        ''')
        card = cards[0]
        repl = card.replacement_effects[0]
        assert repl["action"] == "add_counters"
        assert repl["counter_type"] == "+1/+1"
        assert repl["count"] == 3

    def test_parse_prevent_die(self):
        from mtg_engine.dsl.parser import parse_card
        cards = parse_card('''
            card "Phoenix" {
                type: Creature
                cost: {3}{R}
                p/t: 3 / 3
                replace(die): prevent
            }
        ''')
        card = cards[0]
        repl = card.replacement_effects[0]
        assert repl["type"] == "die"
        assert repl["action"] == "prevent"

    def test_parse_prevent_damage(self):
        from mtg_engine.dsl.parser import parse_card
        cards = parse_card('''
            card "Shield" {
                type: Enchantment
                cost: {1}{W}
                replace(damage, any): prevent_damage(3)
            }
        ''')
        card = cards[0]
        repl = card.replacement_effects[0]
        assert repl["action"] == "prevent_damage"
        assert repl["amount"] == 3
        assert repl["apply_to"] == "any"

    def test_parse_prevent_all_damage(self):
        from mtg_engine.dsl.parser import parse_card
        cards = parse_card('''
            card "Fog" {
                type: Instant
                cost: {G}
                replace(damage): prevent_damage
            }
        ''')
        card = cards[0]
        repl = card.replacement_effects[0]
        assert repl["action"] == "prevent_damage"
        assert "amount" not in repl

    def test_parse_double_life(self):
        from mtg_engine.dsl.parser import parse_card
        cards = parse_card('''
            card "Boon Reflection" {
                type: Enchantment
                cost: {4}{W}
                replace(life_gain, any): double_life
            }
        ''')
        card = cards[0]
        repl = card.replacement_effects[0]
        assert repl["type"] == "life_gain"
        assert repl["action"] == "double_life"
        assert repl["apply_to"] == "any"

    def test_parse_combined_with_other_props(self):
        """Replacement effects coexist with keywords and triggers."""
        from mtg_engine.dsl.parser import parse_card
        cards = parse_card('''
            card "Fancy Hydra" {
                type: Creature
                cost: {4}{G}{G}
                p/t: 0 / 0
                keywords: trample
                replace(enter_battlefield): add_counters("+1/+1", 5)
                when(dies): draw(2)
            }
        ''')
        card = cards[0]
        assert Keyword.TRAMPLE in card.keywords
        assert len(card.replacement_effects) == 1
        assert len(card.triggered_abilities) == 1
