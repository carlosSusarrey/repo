"""Tests for the card DSL parser."""

from mtg_engine.core.enums import CardType
from mtg_engine.dsl import parse_card


class TestDSLParser:
    def test_parse_simple_creature(self):
        dsl = '''
        card "Grizzly Bears" {
            type: Creature
            cost: {1}{G}
            subtype: Bear
            p/t: 2 / 2
        }
        '''
        cards = parse_card(dsl)
        assert len(cards) == 1
        card = cards[0]
        assert card.name == "Grizzly Bears"
        assert card.card_type == CardType.CREATURE
        assert card.power == 2
        assert card.toughness == 2

    def test_parse_instant_with_effect(self):
        dsl = '''
        card "Lightning Bolt" {
            type: Instant
            cost: {R}
            effect: damage(target(any_target), 3)
        }
        '''
        cards = parse_card(dsl)
        assert len(cards) == 1
        card = cards[0]
        assert card.name == "Lightning Bolt"
        assert card.card_type == CardType.INSTANT
        assert len(card.effects) == 1
        assert card.effects[0]["type"] == "damage"
        assert card.effects[0]["amount"] == 3

    def test_parse_multiple_cards(self):
        dsl = '''
        card "Mountain" {
            type: Land
        }
        card "Forest" {
            type: Land
        }
        '''
        cards = parse_card(dsl)
        assert len(cards) == 2

    def test_parse_draw_effect(self):
        dsl = '''
        card "Ancestral Recall" {
            type: Instant
            cost: {U}
            effect: draw(3)
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert card.effects[0]["type"] == "draw"
        assert card.effects[0]["amount"] == 3

    def test_parse_gain_life_effect(self):
        dsl = '''
        card "Healing Salve" {
            type: Instant
            cost: {W}
            effect: gain_life(3)
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert card.effects[0]["type"] == "gain_life"
        assert card.effects[0]["amount"] == 3
