"""Tests for Commander format rules."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.commander import (
    COMMANDER_DAMAGE_THRESHOLD,
    COMMANDER_DECK_SIZE,
    COMMANDER_STARTING_LIFE,
    CommanderState,
    can_cast_from_command_zone,
    check_commander_damage_loss,
    get_color_identity,
    get_commander_tax,
    is_legal_in_deck,
    record_commander_cast,
    record_commander_damage,
    should_go_to_command_zone,
    validate_commander,
    validate_deck,
)
from mtg_engine.core.enums import CardType, Color, SuperType, Zone
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost


def _legendary_creature(name="Commander", cost="2WU"):
    return Card(
        name=name,
        card_type=CardType.CREATURE,
        cost=ManaCost.parse(cost),
        supertypes=[SuperType.LEGENDARY],
        power=3,
        toughness=3,
    )


class TestColorIdentity:
    def test_basic_color_identity(self):
        card = _legendary_creature(cost="{2}{W}{U}")
        identity = get_color_identity(card)
        assert Color.WHITE in identity
        assert Color.BLUE in identity
        assert Color.RED not in identity

    def test_colorless_commander(self):
        card = Card(
            name="Kozilek",
            card_type=CardType.CREATURE,
            cost=ManaCost.parse("{10}"),
            supertypes=[SuperType.LEGENDARY],
            power=12,
            toughness=12,
        )
        identity = get_color_identity(card)
        assert len(identity) == 0

    def test_rules_text_adds_identity(self):
        card = Card(
            name="Kenrith",
            card_type=CardType.CREATURE,
            cost=ManaCost.parse("{4}{W}"),
            supertypes=[SuperType.LEGENDARY],
            power=5,
            toughness=5,
            rules_text="Pay {R}: +1/+1. Pay {G}: Trample. Pay {U}: Draw. Pay {B}: Reanimate.",
        )
        identity = get_color_identity(card)
        assert identity == {Color.WHITE, Color.RED, Color.GREEN, Color.BLUE, Color.BLACK}

    def test_hybrid_mana_identity(self):
        card = Card(
            name="Hybrid Commander",
            card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{W/B}"),
            supertypes=[SuperType.LEGENDARY],
            power=2,
            toughness=2,
        )
        identity = get_color_identity(card)
        assert Color.WHITE in identity
        assert Color.BLACK in identity


class TestValidateCommander:
    def test_valid_commander(self):
        card = _legendary_creature()
        assert validate_commander(card)

    def test_non_legendary_invalid(self):
        card = Card(
            name="Bear",
            card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{G}"),
            power=2,
            toughness=2,
        )
        assert not validate_commander(card)

    def test_legendary_non_creature_invalid(self):
        card = Card(
            name="Legendary Enchantment",
            card_type=CardType.ENCHANTMENT,
            cost=ManaCost.parse("{2}{W}"),
            supertypes=[SuperType.LEGENDARY],
        )
        assert not validate_commander(card)


class TestDeckValidation:
    def test_valid_deck(self):
        commander = _legendary_creature(cost="{2}{W}{U}")
        # 99 cards in deck (100 including commander)
        deck = [
            Card(name=f"Card {i}", card_type=CardType.CREATURE,
                 cost=ManaCost.parse("{1}{W}"), power=1, toughness=1)
            for i in range(99)
        ]
        errors = validate_deck(deck, commander)
        assert len(errors) == 0

    def test_wrong_deck_size(self):
        commander = _legendary_creature()
        deck = [
            Card(name=f"Card {i}", card_type=CardType.CREATURE,
                 cost=ManaCost.parse("{1}"), power=1, toughness=1)
            for i in range(50)
        ]
        errors = validate_deck(deck, commander)
        assert any("100" in e for e in errors)

    def test_color_identity_violation(self):
        commander = _legendary_creature(cost="{2}{W}{U}")
        identity = get_color_identity(commander)
        deck = [
            Card(name=f"Card {i}", card_type=CardType.CREATURE,
                 cost=ManaCost.parse("{1}{W}"), power=1, toughness=1)
            for i in range(98)
        ]
        # Add a red card (outside identity)
        deck.append(Card(
            name="Red Card", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{R}"), power=1, toughness=1,
        ))
        errors = validate_deck(deck, commander)
        assert any("outside" in e.lower() for e in errors)

    def test_singleton_violation(self):
        commander = _legendary_creature(cost="{2}{W}{U}")
        base_card = Card(
            name="Duplicate Card", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{W}"), power=1, toughness=1,
        )
        deck = [base_card] * 99
        errors = validate_deck(deck, commander)
        assert any("Duplicate" in e for e in errors)

    def test_basic_lands_exempt_from_singleton(self):
        commander = _legendary_creature(cost="{2}{W}{U}")
        plains = Card(
            name="Plains", card_type=CardType.LAND,
            supertypes=[SuperType.BASIC],
        )
        deck = [plains] * 99
        errors = validate_deck(deck, commander)
        # No singleton errors for basic lands
        assert not any("Duplicate" in e for e in errors)


class TestCommanderTax:
    def test_initial_no_tax(self):
        state = CommanderState(commander_id="cmd1")
        tax = get_commander_tax(state)
        assert tax.generic == 0

    def test_tax_increases(self):
        state = CommanderState(commander_id="cmd1")
        record_commander_cast(state)
        tax = get_commander_tax(state)
        assert tax.generic == 2

        record_commander_cast(state)
        tax = get_commander_tax(state)
        assert tax.generic == 4


class TestCommanderDamage:
    def test_record_damage(self):
        state = CommanderState(commander_id="cmd1")
        total = record_commander_damage(state, "enemy_cmd", 5)
        assert total == 5

    def test_accumulate_damage(self):
        state = CommanderState(commander_id="cmd1")
        record_commander_damage(state, "enemy_cmd", 10)
        total = record_commander_damage(state, "enemy_cmd", 11)
        assert total == 21

    def test_damage_loss_at_21(self):
        state = CommanderState(commander_id="cmd1")
        record_commander_damage(state, "enemy_cmd", 21)
        result = check_commander_damage_loss(state)
        assert result == "enemy_cmd"

    def test_no_loss_below_21(self):
        state = CommanderState(commander_id="cmd1")
        record_commander_damage(state, "enemy_cmd", 20)
        result = check_commander_damage_loss(state)
        assert result is None

    def test_separate_tracking(self):
        state = CommanderState(commander_id="cmd1")
        record_commander_damage(state, "cmd_a", 15)
        record_commander_damage(state, "cmd_b", 15)
        # Neither has reached 21
        assert check_commander_damage_loss(state) is None


class TestCommandZone:
    def test_cast_from_command_zone(self):
        card = CardInstance(
            card=_legendary_creature(),
            zone=Zone.COMMAND,
            instance_id="cmd1",
        )
        state = CommanderState(commander_id="cmd1")
        assert can_cast_from_command_zone(card, state)

    def test_cannot_cast_from_hand(self):
        card = CardInstance(
            card=_legendary_creature(),
            zone=Zone.HAND,
            instance_id="cmd1",
        )
        state = CommanderState(commander_id="cmd1")
        assert not can_cast_from_command_zone(card, state)

    def test_should_go_to_command_zone(self):
        card = CardInstance(
            card=_legendary_creature(),
            zone=Zone.BATTLEFIELD,
            instance_id="cmd1",
        )
        state = CommanderState(commander_id="cmd1")
        assert should_go_to_command_zone(card, state, Zone.GRAVEYARD)
        assert should_go_to_command_zone(card, state, Zone.EXILE)
        assert not should_go_to_command_zone(card, state, Zone.HAND)

    def test_non_commander_no_redirect(self):
        card = CardInstance(
            card=_legendary_creature(),
            zone=Zone.BATTLEFIELD,
            instance_id="not_cmd",
        )
        state = CommanderState(commander_id="cmd1")
        assert not should_go_to_command_zone(card, state, Zone.GRAVEYARD)


class TestConstants:
    def test_starting_life(self):
        assert COMMANDER_STARTING_LIFE == 40

    def test_damage_threshold(self):
        assert COMMANDER_DAMAGE_THRESHOLD == 21

    def test_deck_size(self):
        assert COMMANDER_DECK_SIZE == 100
