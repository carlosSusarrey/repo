"""Tests for keyword abilities."""

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Color, Zone
from mtg_engine.core.keywords import (
    Keyword, can_block, can_be_destroyed, can_be_targeted_by_opponent,
    has_summoning_sickness_immunity, taps_when_attacking, is_damage_lethal,
)
from mtg_engine.core.mana import ManaCost


class TestKeywordHelpers:
    def test_flying_blocks(self):
        # Flying can be blocked by flying
        assert can_block({Keyword.FLYING}, {Keyword.FLYING})
        # Flying can be blocked by reach
        assert can_block({Keyword.FLYING}, {Keyword.REACH})
        # Flying NOT blocked by ground creature
        assert not can_block({Keyword.FLYING}, set())

    def test_shadow_blocks(self):
        # Shadow only blocked by shadow
        assert can_block({Keyword.SHADOW}, {Keyword.SHADOW})
        assert not can_block({Keyword.SHADOW}, set())
        # Shadow can't block non-shadow
        assert not can_block(set(), {Keyword.SHADOW})

    def test_horsemanship(self):
        assert can_block({Keyword.HORSEMANSHIP}, {Keyword.HORSEMANSHIP})
        assert not can_block({Keyword.HORSEMANSHIP}, set())

    def test_haste_immunity(self):
        assert has_summoning_sickness_immunity({Keyword.HASTE})
        assert not has_summoning_sickness_immunity(set())

    def test_vigilance_no_tap(self):
        assert not taps_when_attacking({Keyword.VIGILANCE})
        assert taps_when_attacking(set())

    def test_deathtouch_lethal(self):
        assert is_damage_lethal(1, 5, source_has_deathtouch=True)
        assert not is_damage_lethal(0, 5, source_has_deathtouch=True)
        assert not is_damage_lethal(4, 5, source_has_deathtouch=False)
        assert is_damage_lethal(5, 5, source_has_deathtouch=False)

    def test_hexproof(self):
        assert not can_be_targeted_by_opponent({Keyword.HEXPROOF})
        assert can_be_targeted_by_opponent(set())

    def test_shroud(self):
        assert not can_be_targeted_by_opponent({Keyword.SHROUD})
        from mtg_engine.core.keywords import can_be_targeted_by_controller
        assert not can_be_targeted_by_controller({Keyword.SHROUD})

    def test_indestructible(self):
        assert not can_be_destroyed({Keyword.INDESTRUCTIBLE})
        assert can_be_destroyed(set())


class TestCardInstanceKeywords:
    def test_base_keywords(self):
        card = Card(
            name="Serra Angel", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{3}{W}{W}"),
            power=4, toughness=4,
            keywords={Keyword.FLYING, Keyword.VIGILANCE},
        )
        inst = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        assert inst.has_keyword(Keyword.FLYING)
        assert inst.has_keyword(Keyword.VIGILANCE)
        assert not inst.has_keyword(Keyword.HASTE)

    def test_granted_keywords(self):
        card = Card(
            name="Bear", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{G}"), power=2, toughness=2,
        )
        inst = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        assert not inst.has_keyword(Keyword.FLYING)

        inst.granted_keywords.add(Keyword.FLYING)
        assert inst.has_keyword(Keyword.FLYING)

    def test_removed_keywords(self):
        card = Card(
            name="Serra Angel", card_type=CardType.CREATURE,
            keywords={Keyword.FLYING, Keyword.VIGILANCE},
            power=4, toughness=4,
        )
        inst = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        inst.removed_keywords.add(Keyword.FLYING)
        assert not inst.has_keyword(Keyword.FLYING)
        assert inst.has_keyword(Keyword.VIGILANCE)

    def test_can_attack_defender(self):
        card = Card(
            name="Wall", card_type=CardType.CREATURE,
            keywords={Keyword.DEFENDER}, power=0, toughness=4,
        )
        inst = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        assert not inst.can_attack()

    def test_can_attack_summoning_sick(self):
        card = Card(name="Bear", card_type=CardType.CREATURE, power=2, toughness=2)
        inst = CardInstance(card=card, zone=Zone.BATTLEFIELD, summoning_sick=True)
        assert not inst.can_attack()

    def test_can_attack_haste_ignores_sickness(self):
        card = Card(
            name="Goblin", card_type=CardType.CREATURE,
            keywords={Keyword.HASTE}, power=2, toughness=2,
        )
        inst = CardInstance(card=card, zone=Zone.BATTLEFIELD, summoning_sick=True)
        assert inst.can_attack()

    def test_clear_end_of_turn(self):
        card = Card(name="Bear", card_type=CardType.CREATURE, power=2, toughness=2)
        inst = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        inst.granted_keywords.add(Keyword.FLYING)
        inst.temp_power_mod = 3
        inst.temp_toughness_mod = 3

        assert inst.current_power == 5
        inst.clear_end_of_turn()
        assert inst.current_power == 2
        assert not inst.has_keyword(Keyword.FLYING)
