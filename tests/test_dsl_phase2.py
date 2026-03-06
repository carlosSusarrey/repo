"""Tests for Phase 2 DSL grammar additions."""

import pytest

from mtg_engine.core.enums import CardType, SuperType
from mtg_engine.core.keywords import Keyword
from mtg_engine.dsl.parser import parse_card


class TestEquipmentDSL:
    def test_parse_equipment(self):
        cards = parse_card('''
        card "Bonesplitter" {
            type: Artifact
            cost: {1}
            subtype: Equipment
            effect: pump(self, +2 / +0)
            equip: {1}
            rules: "Equipped creature gets +2/+0. Equip {1}"
        }
        ''')
        assert len(cards) == 1
        card = cards[0]
        assert card.name == "Bonesplitter"
        assert card.card_type == CardType.ARTIFACT
        assert "Equipment" in card.subtypes
        assert Keyword.EQUIP in card.keyword_params
        assert len(card.effects) == 1
        assert card.effects[0]["type"] == "pump"


class TestAuraDSL:
    def test_parse_aura(self):
        cards = parse_card('''
        card "Pacifism" {
            type: Enchantment
            cost: {1}{W}
            subtype: Aura
            enchant: creature
            rules: "Enchanted creature can't attack or block."
        }
        ''')
        assert len(cards) == 1
        card = cards[0]
        assert card.name == "Pacifism"
        assert card.card_type == CardType.ENCHANTMENT
        assert "Aura" in card.subtypes
        # enchant becomes an effect
        assert any(e.get("type") == "enchant" for e in card.effects)


class TestPlaneswalkerDSL:
    def test_parse_planeswalker(self):
        cards = parse_card('''
        card "Chandra, Torch of Defiance" {
            type: Planeswalker
            cost: {2}{R}{R}
            supertype: Legendary
            subtype: Chandra
            loyalty: 4
            loyalty(+1): damage(each_opponent, 2)
            loyalty(-3): damage(target(creature), 4)
            loyalty(-7): draw(5)
            rules: "+1: Deal 2 to each opponent."
        }
        ''')
        assert len(cards) == 1
        card = cards[0]
        assert card.name == "Chandra, Torch of Defiance"
        assert card.card_type == CardType.PLANESWALKER
        assert card.loyalty == 4
        assert SuperType.LEGENDARY in card.supertypes
        assert len(card.activated_abilities) == 3

        # Check +1 ability
        plus1 = card.activated_abilities[0]
        assert plus1["loyalty_cost"] == 1
        assert plus1["effects"][0]["type"] == "damage"

        # Check -3 ability
        minus3 = card.activated_abilities[1]
        assert minus3["loyalty_cost"] == -3

        # Check -7 ability
        minus7 = card.activated_abilities[2]
        assert minus7["loyalty_cost"] == -7
        assert minus7["effects"][0]["type"] == "draw"


class TestActivatedAbilityDSL:
    def test_parse_activated_ability(self):
        cards = parse_card('''
        card "Llanowar Elves" {
            type: Creature
            cost: {G}
            subtype: Elf
            p/t: 1 / 1
            activate({0}): add_mana(G)
            rules: "Tap: Add G."
        }
        ''')
        assert len(cards) == 1
        card = cards[0]
        assert card.name == "Llanowar Elves"
        assert len(card.activated_abilities) == 1
        ability = card.activated_abilities[0]
        assert ability["effects"][0]["type"] == "add_mana"
        assert ability["effects"][0]["color"] == "G"


class TestAddManaDSL:
    def test_parse_add_mana_effect(self):
        cards = parse_card('''
        card "Sol Ring" {
            type: Artifact
            cost: {1}
            activate({0}): add_mana(C)
            rules: "Tap: Add CC."
        }
        ''')
        card = cards[0]
        assert len(card.activated_abilities) == 1
        assert card.activated_abilities[0]["effects"][0]["type"] == "add_mana"
        assert card.activated_abilities[0]["effects"][0]["color"] == "C"


class TestBasicLandDSL:
    def test_parse_basic_lands(self):
        cards = parse_card('''
        card "Forest" {
            type: Land
            supertype: Basic
            subtype: Forest
            rules: "Tap: Add G."
        }
        ''')
        assert len(cards) == 1
        card = cards[0]
        assert card.card_type == CardType.LAND
        assert SuperType.BASIC in card.supertypes
        assert "Forest" in card.subtypes


class TestFullSampleFile:
    def test_parse_updated_sample_file(self):
        from mtg_engine.dsl.parser import parse_card_file
        cards = parse_card_file("cards/sample.mtg")
        names = [c.name for c in cards]

        # Phase 1 cards
        assert "Lightning Bolt" in names
        assert "Serra Angel" in names

        # Phase 2 cards
        assert "Bonesplitter" in names
        assert "Loxodon Warhammer" in names
        assert "Pacifism" in names
        assert "Rancor" in names
        assert "Chandra, Torch of Defiance" in names
        assert "Plains" in names
        assert "Forest" in names
        assert "Llanowar Elves" in names

        # Check Chandra has loyalty abilities
        chandra = next(c for c in cards if c.name == "Chandra, Torch of Defiance")
        assert chandra.loyalty == 4
        assert len(chandra.activated_abilities) == 3
