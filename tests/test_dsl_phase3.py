"""Tests for Phase 3 DSL grammar and parser additions."""

import pytest

from mtg_engine.core.enums import CardType
from mtg_engine.core.keywords import Keyword
from mtg_engine.dsl.parser import parse_card


class TestSagaDSL:
    def test_parse_saga_chapters(self):
        text = '''
        card "The Eldest Reborn" {
            type: Enchantment
            cost: {4}{B}
            subtype: Saga
            chapter(1): destroy(target(creature))
            chapter(2): draw(1)
            chapter(3): gain_life(5)
        }
        '''
        cards = parse_card(text)
        assert len(cards) == 1
        card = cards[0]
        assert card.name == "The Eldest Reborn"
        assert card.card_type == CardType.ENCHANTMENT
        assert "Saga" in card.subtypes


class TestAdventureDSL:
    def test_parse_adventure(self):
        text = '''
        card "Bonecrusher Giant" {
            type: Creature
            cost: {2}{R}
            p/t: 4/3
            adventure "Stomp" {
                type: Instant
                cost: {1}{R}
                effect: damage(target(any_target), 2)
            }
        }
        '''
        cards = parse_card(text)
        assert len(cards) == 1
        card = cards[0]
        assert card.name == "Bonecrusher Giant"
        assert card.card_type == CardType.CREATURE
        assert card.power == 4


class TestMorphDSL:
    def test_parse_morph_cost(self):
        text = '''
        card "Willbender" {
            type: Creature
            cost: {1}{U}
            p/t: 1/2
            morph: {1}{U}
        }
        '''
        cards = parse_card(text)
        assert len(cards) == 1
        card = cards[0]
        assert card.name == "Willbender"

    def test_parse_disguise_cost(self):
        text = '''
        card "Disguised Agent" {
            type: Creature
            cost: {2}{U}
            p/t: 2/2
            disguise: {1}{U}
        }
        '''
        cards = parse_card(text)
        assert len(cards) == 1


class TestTransformDSL:
    def test_parse_transform_condition(self):
        text = '''
        card "Delver of Secrets" {
            type: Creature
            cost: {U}
            p/t: 1/1
            transform: "reveal instant or sorcery from top of library"
            back_face {
                type: Creature
                p/t: 3/2
                keywords: flying
            }
        }
        '''
        cards = parse_card(text)
        assert len(cards) == 1
        card = cards[0]
        assert card.name == "Delver of Secrets"


class TestNewEffects:
    def test_parse_add_counter(self):
        text = '''
        card "Hunger of the Howlpack" {
            type: Instant
            cost: {G}
            effect: add_counter(target(creature), "+1/+1", 3)
        }
        '''
        cards = parse_card(text)
        assert len(cards) == 1
        assert len(cards[0].effects) == 1
        assert cards[0].effects[0]["type"] == "add_counter"
        assert cards[0].effects[0]["counter_type"] == "+1/+1"
        assert cards[0].effects[0]["amount"] == 3

    def test_parse_mill(self):
        text = '''
        card "Thought Scour" {
            type: Instant
            cost: {U}
            effect: mill(2)
        }
        '''
        cards = parse_card(text)
        assert cards[0].effects[0]["type"] == "mill"
        assert cards[0].effects[0]["amount"] == 2

    def test_parse_scry(self):
        text = '''
        card "Opt" {
            type: Instant
            cost: {U}
            effect: scry(1)
        }
        '''
        cards = parse_card(text)
        assert cards[0].effects[0]["type"] == "scry"

    def test_parse_exile(self):
        text = '''
        card "Path to Exile" {
            type: Instant
            cost: {W}
            effect: exile(target(creature))
        }
        '''
        cards = parse_card(text)
        assert cards[0].effects[0]["type"] == "exile"

    def test_parse_bounce(self):
        text = '''
        card "Unsummon" {
            type: Instant
            cost: {U}
            effect: bounce(target(creature))
        }
        '''
        cards = parse_card(text)
        assert cards[0].effects[0]["type"] == "bounce"

    def test_parse_sacrifice(self):
        text = '''
        card "Diabolic Edict" {
            type: Instant
            cost: {1}{B}
            effect: sacrifice(target(creature))
        }
        '''
        cards = parse_card(text)
        assert cards[0].effects[0]["type"] == "sacrifice"

    def test_parse_x_damage(self):
        text = '''
        card "Fireball" {
            type: Sorcery
            cost: {X}{R}
            effect: x_damage(target(any_target))
        }
        '''
        cards = parse_card(text)
        assert cards[0].effects[0]["type"] == "x_damage"
        assert cards[0].cost.x_count == 1
        assert cards[0].cost.has_x


class TestMultiEffect:
    def test_parse_multi_effect(self):
        text = '''
        card "Electrolyze" {
            type: Instant
            cost: {1}{U}{R}
            effect: damage(target(any_target), 2); draw(1)
        }
        '''
        cards = parse_card(text)
        assert len(cards) == 1
        # Multi-effect should produce a list
        effects = cards[0].effects
        assert len(effects) == 1
        effect = effects[0]
        # Multi-effect stored as a list of effects
        assert isinstance(effect, list)
        assert len(effect) == 2
        assert effect[0]["type"] == "damage"
        assert effect[1]["type"] == "draw"


class TestExtendedManaInDSL:
    def test_parse_hybrid_cost(self):
        text = '''
        card "Kitchen Finks" {
            type: Creature
            cost: {1}{W/G}{W/G}
            p/t: 3/2
            keywords: persist
        }
        '''
        cards = parse_card(text)
        assert len(cards) == 1
        cost = cards[0].cost
        assert cost.generic == 1
        assert len(cost.hybrid) == 2

    def test_parse_phyrexian_cost(self):
        text = '''
        card "Dismember" {
            type: Instant
            cost: {1}{B/P}{B/P}
            effect: pump(target(creature), -5/-5)
        }
        '''
        cards = parse_card(text)
        cost = cards[0].cost
        assert cost.generic == 1
        assert len(cost.phyrexian) == 2

    def test_parse_snow_cost(self):
        text = '''
        card "Icehide Golem" {
            type: Creature
            cost: {S}
            p/t: 2/2
        }
        '''
        cards = parse_card(text)
        cost = cards[0].cost
        assert cost.snow == 1


class TestNewKeywords:
    def test_parse_morph_keyword(self):
        text = '''
        card "Morph Beast" {
            type: Creature
            cost: {3}{G}
            p/t: 4/4
            keywords: morph
        }
        '''
        cards = parse_card(text)
        assert Keyword.MORPH in cards[0].keywords

    def test_parse_persist_keyword(self):
        text = '''
        card "Kitchen Finks" {
            type: Creature
            cost: {1}{W/G}{W/G}
            p/t: 3/2
            keywords: persist
        }
        '''
        cards = parse_card(text)
        assert Keyword.PERSIST in cards[0].keywords

    def test_parse_undying_keyword(self):
        text = '''
        card "Geralf's Messenger" {
            type: Creature
            cost: {B}{B}{B}
            p/t: 3/2
            keywords: undying
        }
        '''
        cards = parse_card(text)
        assert Keyword.UNDYING in cards[0].keywords
