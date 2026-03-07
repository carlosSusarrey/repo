"""Tests for Battle cards."""

import pytest

from mtg_engine.core.battle import (
    BattleState,
    can_attack_battle,
    can_block_for_battle,
    deal_damage_to_battle,
    get_defense,
    get_protector,
    is_battle,
    is_battle_defeated,
    is_siege,
    setup_battle,
)
from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.mana import ManaCost


def _make_battle(defense=5):
    card = Card(
        name="Invasion of Zendikar",
        card_type=CardType.BATTLE,
        cost=ManaCost.parse("{3}{G}"),
        subtypes=["Siege"],
    )
    instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)
    setup_battle(instance, defense=defense, protector_index=1, is_siege=True)
    return instance


def _make_creature(controller=0):
    card = Card(
        name="Bear",
        card_type=CardType.CREATURE,
        cost=ManaCost.parse("{1}{G}"),
        power=2,
        toughness=2,
    )
    return CardInstance(card=card, zone=Zone.BATTLEFIELD, controller_index=controller)


class TestSetupBattle:
    def test_setup(self):
        battle = _make_battle(defense=5)
        assert is_battle(battle)
        assert get_defense(battle) == 5
        assert get_protector(battle) == 1

    def test_is_siege(self):
        battle = _make_battle()
        assert is_siege(battle)

    def test_defense_counters_set(self):
        battle = _make_battle(defense=7)
        assert battle.counters["defense"] == 7

    def test_not_battle_by_default(self):
        card = Card(name="Bear", card_type=CardType.CREATURE, power=2, toughness=2)
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        assert not is_battle(instance)


class TestDamageToBattle:
    def test_deal_damage(self):
        battle = _make_battle(defense=5)
        remaining = deal_damage_to_battle(battle, 3)
        assert remaining == 2
        assert get_defense(battle) == 2

    def test_deal_lethal_damage(self):
        battle = _make_battle(defense=5)
        remaining = deal_damage_to_battle(battle, 5)
        assert remaining == 0
        assert is_battle_defeated(battle)

    def test_deal_excess_damage(self):
        battle = _make_battle(defense=3)
        remaining = deal_damage_to_battle(battle, 10)
        assert remaining == 0

    def test_deal_zero_damage(self):
        battle = _make_battle(defense=5)
        remaining = deal_damage_to_battle(battle, 0)
        assert remaining == 5

    def test_not_defeated_with_defense(self):
        battle = _make_battle(defense=5)
        deal_damage_to_battle(battle, 2)
        assert not is_battle_defeated(battle)


class TestAttackingBattle:
    def test_can_attack_as_non_protector(self):
        battle = _make_battle()  # Protector is player 1
        attacker = _make_creature(controller=0)  # Player 0
        assert can_attack_battle(attacker, battle)

    def test_protector_cannot_attack_own_battle(self):
        battle = _make_battle()  # Protector is player 1
        attacker = _make_creature(controller=1)  # Player 1 is protector
        assert not can_attack_battle(attacker, battle)

    def test_cannot_attack_non_battlefield_battle(self):
        card = Card(
            name="Battle",
            card_type=CardType.BATTLE,
            cost=ManaCost.parse("{3}"),
        )
        battle = CardInstance(card=card, zone=Zone.GRAVEYARD)
        setup_battle(battle, defense=5, protector_index=1)
        attacker = _make_creature(controller=0)
        assert not can_attack_battle(attacker, battle)


class TestBlockingForBattle:
    def test_protector_can_block(self):
        battle = _make_battle()  # Protector is player 1
        blocker = _make_creature(controller=1)
        assert can_block_for_battle(blocker, battle)

    def test_non_protector_cannot_block(self):
        battle = _make_battle()  # Protector is player 1
        blocker = _make_creature(controller=0)
        assert not can_block_for_battle(blocker, battle)


class TestBattleSBA:
    def test_battle_sba(self):
        """Verify battle defeated is caught as SBA."""
        from mtg_engine.core.game_state import GameState
        from mtg_engine.core.player import Player

        state = GameState()
        state.players.append(Player(name="Alice"))
        state.players.append(Player(name="Bob"))

        battle_card = Card(
            name="Invasion",
            card_type=CardType.BATTLE,
            cost=ManaCost.parse("{3}"),
        )
        battle = CardInstance(
            card=battle_card,
            zone=Zone.BATTLEFIELD,
            owner_index=0,
            controller_index=0,
        )
        battle.counters["defense"] = 0
        state.cards.append(battle)

        actions = state.check_state_based_actions()
        assert any("exiled" in a.lower() or "defense" in a.lower() for a in actions)
        assert battle.zone == Zone.EXILE
