"""Tests for multi-type cards and Kindred type."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.mana import ManaCost
from mtg_engine.dsl.parser import parse_card


class TestMultiTypeCard:
    def test_single_type_defaults(self):
        card = Card(name="Bear", card_type=CardType.CREATURE)
        assert card.card_types == [CardType.CREATURE]
        assert card.card_type == CardType.CREATURE

    def test_multi_type_via_card_types(self):
        card = Card(
            name="Solemn Simulacrum",
            card_types=[CardType.ARTIFACT, CardType.CREATURE],
            cost=ManaCost.parse("{4}"),
            power=2,
            toughness=2,
        )
        assert card.is_artifact
        assert card.is_creature
        assert not card.is_enchantment
        assert card.card_type in card.card_types

    def test_has_type(self):
        card = Card(
            name="Dryad Arbor",
            card_types=[CardType.LAND, CardType.CREATURE],
            power=1,
            toughness=1,
        )
        assert card.has_type(CardType.LAND)
        assert card.has_type(CardType.CREATURE)
        assert not card.has_type(CardType.ARTIFACT)

    def test_post_init_syncs_card_type(self):
        card = Card(
            name="Test",
            card_type=CardType.INSTANT,
            card_types=[CardType.ARTIFACT, CardType.CREATURE],
        )
        # card_type should be updated to first of card_types
        assert card.card_type == CardType.ARTIFACT

    def test_post_init_single_type(self):
        card = Card(name="Bear", card_type=CardType.CREATURE)
        assert card.card_types == [CardType.CREATURE]


class TestKindredType:
    def test_kindred_in_card_types(self):
        card = Card(
            name="Kindred Summons",
            card_types=[CardType.KINDRED, CardType.INSTANT],
            cost=ManaCost.parse("{5}{G}{G}"),
        )
        assert card.has_type(CardType.KINDRED)
        assert card.has_type(CardType.INSTANT)


class TestMultiTypeDSL:
    def test_parse_single_type(self):
        text = '''
        card "Bear" {
            type: Creature
            cost: {1}{G}
            p/t: 2/2
        }
        '''
        cards = parse_card(text)
        assert len(cards) == 1
        assert cards[0].card_type == CardType.CREATURE
        assert cards[0].card_types == [CardType.CREATURE]

    def test_parse_multi_type(self):
        text = '''
        card "Solemn Simulacrum" {
            type: Artifact Creature
            cost: {4}
            p/t: 2/2
        }
        '''
        cards = parse_card(text)
        assert len(cards) == 1
        assert cards[0].is_artifact
        assert cards[0].is_creature
        assert cards[0].card_types == [CardType.ARTIFACT, CardType.CREATURE]

    def test_parse_kindred(self):
        text = '''
        card "Kindred Charge" {
            type: Kindred Sorcery
            cost: {4}{R}{R}
        }
        '''
        cards = parse_card(text)
        assert len(cards) == 1
        assert cards[0].has_type(CardType.KINDRED)
        assert cards[0].has_type(CardType.SORCERY)

    def test_parse_enchantment_creature(self):
        text = '''
        card "Courser of Kruphix" {
            type: Enchantment Creature
            cost: {1}{G}{G}
            p/t: 2/4
        }
        '''
        cards = parse_card(text)
        assert len(cards) == 1
        assert cards[0].is_enchantment
        assert cards[0].is_creature


class TestCardInstanceToken:
    def test_token_flag(self):
        card = Card(name="Goblin", card_type=CardType.CREATURE, power=1, toughness=1)
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD, is_token=True)
        assert instance.is_token

    def test_non_token_default(self):
        card = Card(name="Bear", card_type=CardType.CREATURE, power=2, toughness=2)
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        assert not instance.is_token
