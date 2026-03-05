"""Tests for the card DSL parser."""

from mtg_engine.core.enums import CardType
from mtg_engine.core.keywords import Keyword
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

    def test_parse_keywords(self):
        dsl = '''
        card "Serra Angel" {
            type: Creature
            cost: {3}{W}{W}
            p/t: 4 / 4
            keywords: flying, vigilance
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert Keyword.FLYING in card.keywords
        assert Keyword.VIGILANCE in card.keywords

    def test_parse_many_keywords(self):
        dsl = '''
        card "Vampire Nighthawk" {
            type: Creature
            cost: {1}{B}{B}
            p/t: 2 / 3
            keywords: flying, deathtouch, lifelink
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert Keyword.FLYING in card.keywords
        assert Keyword.DEATHTOUCH in card.keywords
        assert Keyword.LIFELINK in card.keywords
        assert len(card.keywords) == 3

    def test_parse_triggered_ability(self):
        dsl = '''
        card "Wall of Omens" {
            type: Creature
            cost: {1}{W}
            p/t: 0 / 4
            keywords: defender
            when(enters_battlefield): draw(1)
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert Keyword.DEFENDER in card.keywords
        assert len(card.triggered_abilities) == 1
        trigger = card.triggered_abilities[0]
        assert trigger["trigger"] == "enters_battlefield"
        assert trigger["effects"][0]["type"] == "draw"

    def test_parse_pump_effect(self):
        dsl = '''
        card "Giant Growth" {
            type: Instant
            cost: {G}
            effect: pump(target(creature), +3 / +3)
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert card.effects[0]["type"] == "pump"
        assert card.effects[0]["power"] == 3
        assert card.effects[0]["toughness"] == 3

    def test_parse_flash(self):
        dsl = '''
        card "Ambush Viper" {
            type: Creature
            cost: {1}{G}
            p/t: 2 / 1
            keywords: flash, deathtouch
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert Keyword.FLASH in card.keywords
        assert Keyword.DEATHTOUCH in card.keywords

    def test_parse_full_sample_file(self):
        """Parse the full sample.mtg file to ensure it's valid."""
        from mtg_engine.dsl import parse_card_file
        cards = parse_card_file("cards/sample.mtg")
        assert len(cards) >= 10
        # Check Serra Angel has keywords
        serra = [c for c in cards if c.name == "Serra Angel"][0]
        assert Keyword.FLYING in serra.keywords
        assert Keyword.VIGILANCE in serra.keywords
