"""Tests for the natural-language rules text translator."""

import pytest

from mtg_engine.core.filters import parse_controller_qualifier, matches_controller
from mtg_engine.core.keywords import Keyword
from mtg_engine.dsl.rules_parser import translate_rules_text
from mtg_engine.dsl import parse_card


# ---- Keyword detection ----

class TestKeywords:
    def test_single_keyword(self):
        result = translate_rules_text("Flying")
        assert Keyword.FLYING in result["keywords"]

    def test_multiple_keywords(self):
        result = translate_rules_text("Flying, first strike, lifelink")
        assert result["keywords"] == {Keyword.FLYING, Keyword.FIRST_STRIKE, Keyword.LIFELINK}

    def test_defender(self):
        result = translate_rules_text("Defender")
        assert Keyword.DEFENDER in result["keywords"]

    def test_keywords_no_effects(self):
        result = translate_rules_text("Trample, haste")
        assert len(result["effects"]) == 0
        assert len(result["triggered_abilities"]) == 0


# ---- Simple effects (instants/sorceries) ----

class TestSimpleEffects:
    def test_damage_any_target(self):
        result = translate_rules_text("Deal 3 damage to any target.")
        assert len(result["effects"]) == 1
        e = result["effects"][0]
        assert e["type"] == "damage"
        assert e["amount"] == 3
        assert e["target"]["kind"] == "target"
        assert e["target"]["target_type"] == "any_target"

    def test_damage_target_creature(self):
        result = translate_rules_text("Deal 5 damage to target creature.")
        e = result["effects"][0]
        assert e["type"] == "damage"
        assert e["amount"] == 5
        assert e["target"]["target_type"] == "creature"

    def test_damage_each_opponent(self):
        result = translate_rules_text("Deal 2 damage to each opponent.")
        e = result["effects"][0]
        assert e["target"]["kind"] == "each_opponent"

    def test_x_damage(self):
        result = translate_rules_text("Deal X damage to any target.")
        e = result["effects"][0]
        assert e["type"] == "x_damage"

    def test_draw_cards(self):
        result = translate_rules_text("Draw 3 cards.")
        e = result["effects"][0]
        assert e["type"] == "draw"
        assert e["amount"] == 3

    def test_draw_a_card(self):
        result = translate_rules_text("Draw a card.")
        e = result["effects"][0]
        assert e["type"] == "draw"
        assert e["amount"] == 1

    def test_gain_life(self):
        result = translate_rules_text("Gain 3 life.")
        e = result["effects"][0]
        assert e["type"] == "gain_life"
        assert e["amount"] == 3

    def test_each_opponent_loses_life(self):
        result = translate_rules_text("Each opponent loses 2 life.")
        e = result["effects"][0]
        assert e["type"] == "lose_life"
        assert e["target"]["kind"] == "each_opponent"
        assert e["amount"] == 2

    def test_destroy_target_creature(self):
        result = translate_rules_text("Destroy target creature.")
        e = result["effects"][0]
        assert e["type"] == "destroy"
        assert e["target"]["target_type"] == "creature"

    def test_exile_target_creature(self):
        result = translate_rules_text("Exile target creature.")
        e = result["effects"][0]
        assert e["type"] == "exile"
        assert e["target"]["target_type"] == "creature"

    def test_bounce(self):
        result = translate_rules_text("Return target creature to its owner's hand.")
        e = result["effects"][0]
        assert e["type"] == "bounce"
        assert e["target"]["target_type"] == "creature"

    def test_counter_spell(self):
        result = translate_rules_text("Counter target spell.")
        e = result["effects"][0]
        assert e["type"] == "counter"
        assert e["target"]["target_type"] == "spell"

    def test_pump(self):
        result = translate_rules_text("Target creature gets +3/+3 until end of turn.")
        e = result["effects"][0]
        assert e["type"] == "pump"
        assert e["power"] == 3
        assert e["toughness"] == 3

    def test_scry(self):
        result = translate_rules_text("Scry 2.")
        e = result["effects"][0]
        assert e["type"] == "scry"
        assert e["amount"] == 2

    def test_mill(self):
        result = translate_rules_text("Mill 3.")
        e = result["effects"][0]
        assert e["type"] == "mill"
        assert e["amount"] == 3

    def test_tap_target(self):
        result = translate_rules_text("Tap target creature.")
        e = result["effects"][0]
        assert e["type"] == "tap"
        assert e["target"]["target_type"] == "creature"

    def test_create_token(self):
        result = translate_rules_text("Create a 1/1 Soldier creature token.")
        e = result["effects"][0]
        assert e["type"] == "create_token"
        assert e["power"] == 1
        assert e["toughness"] == 1

    def test_number_words(self):
        result = translate_rules_text("Draw two cards.")
        assert result["effects"][0]["amount"] == 2


# ---- Triggered abilities ----

class TestTriggeredAbilities:
    def test_etb_draw(self):
        result = translate_rules_text("When ~ enters the battlefield, draw a card.")
        assert len(result["triggered_abilities"]) == 1
        t = result["triggered_abilities"][0]
        assert t["trigger"] == "enters_battlefield"
        assert t["effects"][0]["type"] == "draw"
        assert t["effects"][0]["amount"] == 1

    def test_dies_lose_life(self):
        result = translate_rules_text("When ~ dies, each opponent loses 2 life.")
        t = result["triggered_abilities"][0]
        assert t["trigger"] == "dies"
        assert t["effects"][0]["type"] == "lose_life"

    def test_attacks_damage(self):
        result = translate_rules_text("Whenever ~ attacks, deal 1 damage to each opponent.")
        t = result["triggered_abilities"][0]
        assert t["trigger"] == "attacks"
        assert t["effects"][0]["type"] == "damage"

    def test_upkeep_trigger(self):
        result = translate_rules_text("At the beginning of your upkeep, draw a card.")
        t = result["triggered_abilities"][0]
        assert t["trigger"] == "begin_upkeep"
        assert t["effects"][0]["type"] == "draw"

    def test_etb_gain_life(self):
        result = translate_rules_text("When this creature enters the battlefield, gain 3 life.")
        t = result["triggered_abilities"][0]
        assert t["trigger"] == "enters_battlefield"
        assert t["effects"][0]["type"] == "gain_life"
        assert t["effects"][0]["amount"] == 3


# ---- Activated abilities ----

class TestActivatedAbilities:
    def test_tap_add_mana(self):
        result = translate_rules_text("Tap: Add G.")
        assert len(result["activated_abilities"]) == 1
        a = result["activated_abilities"][0]
        assert a["cost"]["tap"] is True
        assert a["effects"][0]["type"] == "add_mana"
        assert a["effects"][0]["color"] == "G"

    def test_tap_symbol_add_mana(self):
        result = translate_rules_text("{T}: Add {W}.")
        a = result["activated_abilities"][0]
        assert a["cost"]["tap"] is True
        assert a["effects"][0]["type"] == "add_mana"
        assert a["effects"][0]["color"] == "W"

    def test_mana_cost_activated(self):
        result = translate_rules_text("{2}{R}: Deal 2 damage to any target.")
        a = result["activated_abilities"][0]
        assert a["cost"]["mana"] == "{2}{R}"
        assert a["effects"][0]["type"] == "damage"
        assert a["effects"][0]["amount"] == 2


# ---- Mixed rules text ----

class TestMixedRulesText:
    def test_keywords_plus_trigger(self):
        result = translate_rules_text("Defender. When ~ enters the battlefield, draw a card.")
        assert Keyword.DEFENDER in result["keywords"]
        assert len(result["triggered_abilities"]) == 1
        assert result["triggered_abilities"][0]["effects"][0]["type"] == "draw"

    def test_keywords_plus_effect(self):
        result = translate_rules_text("Flying. Deal 3 damage to any target.")
        assert Keyword.FLYING in result["keywords"]
        assert result["effects"][0]["type"] == "damage"

    def test_multiple_keywords_sentence(self):
        result = translate_rules_text("Flying, vigilance")
        assert result["keywords"] == {Keyword.FLYING, Keyword.VIGILANCE}


# ---- Integration with parse_card (rules-only cards) ----

class TestIntegration:
    def test_rules_only_instant(self):
        dsl = '''
        card "Shock" {
            type: Instant
            cost: {R}
            rules: "Deal 2 damage to any target."
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert len(card.effects) == 1
        assert card.effects[0]["type"] == "damage"
        assert card.effects[0]["amount"] == 2
        assert card.effects[0]["target"]["target_type"] == "any_target"

    def test_rules_only_creature_with_keywords(self):
        dsl = '''
        card "Angel" {
            type: Creature
            cost: {3}{W}{W}
            p/t: 4 / 4
            rules: "Flying, vigilance"
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert Keyword.FLYING in card.keywords
        assert Keyword.VIGILANCE in card.keywords

    def test_rules_only_etb_creature(self):
        dsl = '''
        card "Elvish Visionary" {
            type: Creature
            cost: {1}{G}
            p/t: 1 / 1
            rules: "When ~ enters the battlefield, draw a card."
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert len(card.triggered_abilities) == 1
        assert card.triggered_abilities[0]["trigger"] == "enters_battlefield"
        assert card.triggered_abilities[0]["effects"][0]["type"] == "draw"

    def test_rules_only_mana_dork(self):
        dsl = '''
        card "Llanowar Elves" {
            type: Creature
            cost: {G}
            p/t: 1 / 1
            rules: "{T}: Add {G}."
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert len(card.activated_abilities) == 1
        assert card.activated_abilities[0]["effects"][0]["type"] == "add_mana"
        assert card.activated_abilities[0]["effects"][0]["color"] == "G"

    def test_explicit_effects_not_overwritten(self):
        dsl = '''
        card "Lightning Bolt" {
            type: Instant
            cost: {R}
            rules: "Deal 3 damage to any target."
            effect: damage(target(any_target), 3)
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        # Only the explicit effect, not doubled
        assert len(card.effects) == 1

    def test_explicit_keywords_not_overwritten(self):
        dsl = '''
        card "Bird" {
            type: Creature
            cost: {W}
            p/t: 1 / 1
            rules: "Flying"
            keywords: flying
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert card.keywords == {Keyword.FLYING}

    def test_rules_only_draw_spell(self):
        dsl = '''
        card "Ancestral Recall" {
            type: Instant
            cost: {U}
            rules: "Draw 3 cards."
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert len(card.effects) == 1
        assert card.effects[0]["type"] == "draw"
        assert card.effects[0]["amount"] == 3

    def test_rules_only_counter(self):
        dsl = '''
        card "Counterspell" {
            type: Instant
            cost: {U}{U}
            rules: "Counter target spell."
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert len(card.effects) == 1
        assert card.effects[0]["type"] == "counter"

    def test_rules_only_pump(self):
        dsl = '''
        card "Giant Growth" {
            type: Instant
            cost: {G}
            rules: "Target creature gets +3/+3 until end of turn."
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert len(card.effects) == 1
        assert card.effects[0]["type"] == "pump"
        assert card.effects[0]["power"] == 3
        assert card.effects[0]["toughness"] == 3

    def test_rules_only_mixed_keywords_and_trigger(self):
        dsl = '''
        card "Wall of Omens" {
            type: Creature
            cost: {1}{W}
            p/t: 0 / 4
            rules: "Defender. When ~ enters the battlefield, draw a card."
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert Keyword.DEFENDER in card.keywords
        assert len(card.triggered_abilities) == 1
        assert card.triggered_abilities[0]["effects"][0]["type"] == "draw"

    def test_rules_only_gain_life(self):
        dsl = '''
        card "Healing Salve" {
            type: Instant
            cost: {W}
            rules: "Gain 3 life."
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert len(card.effects) == 1
        assert card.effects[0]["type"] == "gain_life"
        assert card.effects[0]["amount"] == 3

    def test_dsl_target_with_controller_qualifier(self):
        dsl = '''
        card "Terminate" {
            type: Instant
            cost: {B}{R}
            effect: destroy(target(creature, opponent))
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert card.effects[0]["target"]["controller"] == "opponent"
        assert card.effects[0]["target"]["target_type"] == "creature"


# ---- Controller qualifier tests ----

class TestControllerQualifiers:
    def test_parse_you_dont_control(self):
        assert parse_controller_qualifier("target creature you don't control") == "opponent"

    def test_parse_you_control(self):
        assert parse_controller_qualifier("target creature you control") == "you"

    def test_parse_opponent_controls(self):
        assert parse_controller_qualifier("target creature an opponent controls") == "opponent"

    def test_parse_no_qualifier(self):
        assert parse_controller_qualifier("target creature") is None

    def test_matches_controller_you(self):
        assert matches_controller("you", target_controller=0, caster_controller=0) is True
        assert matches_controller("you", target_controller=1, caster_controller=0) is False

    def test_matches_controller_opponent(self):
        assert matches_controller("opponent", target_controller=1, caster_controller=0) is True
        assert matches_controller("opponent", target_controller=0, caster_controller=0) is False

    def test_matches_controller_none(self):
        assert matches_controller(None, target_controller=0, caster_controller=1) is True

    def test_damage_you_dont_control(self):
        result = translate_rules_text("Deal 3 damage to target creature you don't control.")
        e = result["effects"][0]
        assert e["type"] == "damage"
        assert e["target"]["target_type"] == "creature"
        assert e["target"]["controller"] == "opponent"

    def test_destroy_you_dont_control(self):
        result = translate_rules_text("Destroy target creature you don't control.")
        e = result["effects"][0]
        assert e["type"] == "destroy"
        assert e["target"]["controller"] == "opponent"

    def test_exile_opponent_controls(self):
        result = translate_rules_text("Exile target creature an opponent controls.")
        e = result["effects"][0]
        assert e["type"] == "exile"
        assert e["target"]["controller"] == "opponent"

    def test_bounce_you_control(self):
        result = translate_rules_text("Return target creature you control to its owner's hand.")
        e = result["effects"][0]
        assert e["type"] == "bounce"
        assert e["target"]["controller"] == "you"

    def test_tap_you_dont_control(self):
        result = translate_rules_text("Tap target creature you don't control.")
        e = result["effects"][0]
        assert e["type"] == "tap"
        assert e["target"]["controller"] == "opponent"

    def test_pump_you_control(self):
        result = translate_rules_text("Target creature you control gets +2/+2 until end of turn.")
        e = result["effects"][0]
        assert e["type"] == "pump"
        assert e["target"]["controller"] == "you"

    def test_no_qualifier_has_no_controller_key(self):
        result = translate_rules_text("Destroy target creature.")
        e = result["effects"][0]
        assert "controller" not in e["target"]

    def test_integration_rules_only_with_qualifier(self):
        dsl = '''
        card "Dark Banishing" {
            type: Instant
            cost: {2}{B}
            rules: "Destroy target creature you don't control."
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert card.effects[0]["type"] == "destroy"
        assert card.effects[0]["target"]["controller"] == "opponent"
        assert card.effects[0]["target"]["target_type"] == "creature"


# ---- State qualifier tests ----

class TestStateQualifiers:
    def test_destroy_target_attacking_creature(self):
        result = translate_rules_text("Destroy target attacking creature.")
        e = result["effects"][0]
        assert e["type"] == "destroy"
        assert e["target"]["target_type"] == "creature"
        assert e["target"]["state"] == "attacking"

    def test_exile_target_tapped_creature(self):
        result = translate_rules_text("Exile target tapped creature.")
        e = result["effects"][0]
        assert e["type"] == "exile"
        assert e["target"]["target_type"] == "creature"
        assert e["target"]["state"] == "tapped"

    def test_tap_target_untapped_creature(self):
        result = translate_rules_text("Tap target untapped creature.")
        e = result["effects"][0]
        assert e["type"] == "tap"
        assert e["target"]["state"] == "untapped"

    def test_bounce_target_attacking_creature(self):
        result = translate_rules_text("Return target attacking creature to its owner's hand.")
        e = result["effects"][0]
        assert e["type"] == "bounce"
        assert e["target"]["state"] == "attacking"

    def test_pump_target_attacking_creature(self):
        result = translate_rules_text("Target attacking creature gets +3/+3 until end of turn.")
        e = result["effects"][0]
        assert e["type"] == "pump"
        assert e["target"]["state"] == "attacking"
        assert e["power"] == 3

    def test_destroy_target_blocking_creature(self):
        result = translate_rules_text("Destroy target blocking creature.")
        e = result["effects"][0]
        assert e["type"] == "destroy"
        assert e["target"]["state"] == "blocking"

    def test_no_state_has_no_state_key(self):
        result = translate_rules_text("Destroy target creature.")
        e = result["effects"][0]
        assert "state" not in e["target"]

    def test_state_and_controller_combined(self):
        result = translate_rules_text("Destroy target attacking creature you don't control.")
        e = result["effects"][0]
        assert e["type"] == "destroy"
        assert e["target"]["state"] == "attacking"
        assert e["target"]["controller"] == "opponent"

    def test_damage_target_attacking_creature(self):
        result = translate_rules_text("Deal 3 damage to target attacking creature.")
        e = result["effects"][0]
        assert e["type"] == "damage"
        assert e["amount"] == 3
        assert e["target"]["target_type"] == "creature"
        assert e["target"]["state"] == "attacking"

    def test_damage_target_creature_opponent(self):
        result = translate_rules_text("Deal 2 damage to target creature an opponent controls.")
        e = result["effects"][0]
        assert e["type"] == "damage"
        assert e["target"]["target_type"] == "creature"
        assert e["target"]["controller"] == "opponent"

    def test_damage_target_tapped_creature_opponent(self):
        result = translate_rules_text("Deal 4 damage to target tapped creature you don't control.")
        e = result["effects"][0]
        assert e["type"] == "damage"
        assert e["amount"] == 4
        assert e["target"]["target_type"] == "creature"
        assert e["target"]["state"] == "tapped"
        assert e["target"]["controller"] == "opponent"


# ---- "All" quantifier tests ----

class TestAllQuantifier:
    def test_destroy_all_creatures(self):
        result = translate_rules_text("Destroy all creatures.")
        e = result["effects"][0]
        assert e["type"] == "destroy"
        assert e["target"]["kind"] == "all"
        assert e["target"]["target_type"] == "creature"

    def test_exile_all_attacking_creatures(self):
        result = translate_rules_text("Exile all attacking creatures.")
        e = result["effects"][0]
        assert e["type"] == "exile"
        assert e["target"]["kind"] == "all"
        assert e["target"]["target_type"] == "creature"
        assert e["target"]["state"] == "attacking"

    def test_destroy_all_artifacts(self):
        result = translate_rules_text("Destroy all artifacts.")
        e = result["effects"][0]
        assert e["type"] == "destroy"
        assert e["target"]["kind"] == "all"
        assert e["target"]["target_type"] == "artifact"

    def test_bounce_all_creatures(self):
        result = translate_rules_text("Return all creatures to their owners' hands.")
        e = result["effects"][0]
        assert e["type"] == "bounce"
        assert e["target"]["kind"] == "all"
        assert e["target"]["target_type"] == "creature"

    def test_tap_all_creatures(self):
        result = translate_rules_text("Tap all creatures.")
        e = result["effects"][0]
        assert e["type"] == "tap"
        assert e["target"]["kind"] == "all"
        assert e["target"]["target_type"] == "creature"

    def test_all_creatures_get_pump(self):
        result = translate_rules_text("All creatures get +1/+1 until end of turn.")
        e = result["effects"][0]
        assert e["type"] == "pump"
        assert e["target"]["kind"] == "all"
        assert e["target"]["target_type"] == "creature"
        assert e["power"] == 1
        assert e["toughness"] == 1

    def test_destroy_all_tapped_creatures(self):
        result = translate_rules_text("Destroy all tapped creatures.")
        e = result["effects"][0]
        assert e["type"] == "destroy"
        assert e["target"]["kind"] == "all"
        assert e["target"]["state"] == "tapped"

    def test_dsl_target_with_state_qualifier(self):
        dsl = '''
        card "Smite" {
            type: Instant
            cost: {W}
            effect: destroy(target(creature, attacking))
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert card.effects[0]["target"]["state"] == "attacking"
        assert card.effects[0]["target"]["target_type"] == "creature"

    def test_dsl_all_with_state_qualifier(self):
        dsl = '''
        card "Wrath of Attackers" {
            type: Sorcery
            cost: {2}{W}{W}
            effect: destroy(all(creature, attacking))
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert card.effects[0]["target"]["kind"] == "all"
        assert card.effects[0]["target"]["state"] == "attacking"

    def test_dsl_all_plain(self):
        dsl = '''
        card "Wrath of God" {
            type: Sorcery
            cost: {2}{W}{W}
            effect: destroy(all(creature))
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert card.effects[0]["target"]["kind"] == "all"
        assert card.effects[0]["target"]["target_type"] == "creature"
