"""Tests for poison counters, infect, toxic, and wither."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost
from mtg_engine.core.player import Player
from mtg_engine.core.poison import (
    POISON_LOSS_THRESHOLD,
    add_poison_counters,
    apply_infect_damage_to_creature,
    apply_infect_damage_to_player,
    apply_toxic_damage,
    apply_wither_damage_to_creature,
    check_poison_loss,
    get_poison_counters,
    get_toxic_amount,
    has_infect,
    has_toxic,
    has_wither,
    should_deal_minus_counters,
    should_deal_poison,
)


def _make_creature(name="Bear", keywords=None, keyword_params=None):
    card = Card(
        name=name,
        card_type=CardType.CREATURE,
        cost=ManaCost.parse("{1}{G}"),
        power=2,
        toughness=2,
        keywords=keywords or set(),
        keyword_params=keyword_params or {},
    )
    return CardInstance(card=card, zone=Zone.BATTLEFIELD)


class TestPoisonCounters:
    def test_initial_poison(self):
        player = Player(name="Alice")
        assert get_poison_counters(player) == 0

    def test_add_poison(self):
        player = Player(name="Alice")
        total = add_poison_counters(player, 3)
        assert total == 3
        assert get_poison_counters(player) == 3

    def test_accumulate_poison(self):
        player = Player(name="Alice")
        add_poison_counters(player, 3)
        add_poison_counters(player, 4)
        assert get_poison_counters(player) == 7

    def test_poison_loss_at_10(self):
        player = Player(name="Alice")
        add_poison_counters(player, 9)
        assert not check_poison_loss(player)
        add_poison_counters(player, 1)
        assert check_poison_loss(player)

    def test_poison_loss_over_10(self):
        player = Player(name="Alice")
        add_poison_counters(player, 15)
        assert check_poison_loss(player)

    def test_threshold_is_10(self):
        assert POISON_LOSS_THRESHOLD == 10


class TestInfect:
    def test_has_infect(self):
        creature = _make_creature(keywords={Keyword.INFECT})
        assert has_infect(creature)

    def test_no_infect(self):
        creature = _make_creature()
        assert not has_infect(creature)

    def test_infect_damage_to_player(self):
        creature = _make_creature(keywords={Keyword.INFECT})
        player = Player(name="Alice")
        result = apply_infect_damage_to_player(creature, player, 3)
        assert result["poison_added"] == 3
        assert get_poison_counters(player) == 3
        # Life should NOT change (caller is responsible for not calling lose_life)
        assert player.life == 20

    def test_infect_damage_to_creature(self):
        creature = _make_creature(keywords={Keyword.INFECT})
        target = _make_creature(name="Target")
        result = apply_infect_damage_to_creature(creature, target, 2)
        assert result["counters_added"] == 2
        assert target.counters.get("-1/-1") == 2
        # Damage should NOT be marked
        assert target.damage_marked == 0

    def test_infect_zero_damage(self):
        creature = _make_creature(keywords={Keyword.INFECT})
        player = Player(name="Alice")
        result = apply_infect_damage_to_player(creature, player, 0)
        assert result["poison_added"] == 0

    def test_should_deal_poison(self):
        infect = _make_creature(keywords={Keyword.INFECT})
        normal = _make_creature()
        assert should_deal_poison(infect)
        assert not should_deal_poison(normal)

    def test_should_deal_minus_counters(self):
        infect = _make_creature(keywords={Keyword.INFECT})
        wither = _make_creature(keywords={Keyword.WITHER})
        normal = _make_creature()
        assert should_deal_minus_counters(infect)
        assert should_deal_minus_counters(wither)
        assert not should_deal_minus_counters(normal)


class TestWither:
    def test_has_wither(self):
        creature = _make_creature(keywords={Keyword.WITHER})
        assert has_wither(creature)

    def test_infect_implies_wither(self):
        creature = _make_creature(keywords={Keyword.INFECT})
        assert has_wither(creature)

    def test_wither_damage_to_creature(self):
        creature = _make_creature(keywords={Keyword.WITHER})
        target = _make_creature(name="Target")
        result = apply_wither_damage_to_creature(creature, target, 3)
        assert result["counters_added"] == 3
        assert target.counters.get("-1/-1") == 3


class TestToxic:
    def test_has_toxic(self):
        creature = _make_creature(keywords={Keyword.TOXIC})
        assert has_toxic(creature)

    def test_get_toxic_amount(self):
        creature = _make_creature(
            keywords={Keyword.TOXIC},
            keyword_params={Keyword.TOXIC: 2},
        )
        assert get_toxic_amount(creature) == 2

    def test_toxic_default_amount(self):
        creature = _make_creature(keywords={Keyword.TOXIC})
        assert get_toxic_amount(creature) == 0

    def test_apply_toxic_damage(self):
        creature = _make_creature(keywords={Keyword.TOXIC})
        player = Player(name="Alice")
        result = apply_toxic_damage(creature, player, 3)
        assert result["poison_added"] == 3
        assert get_poison_counters(player) == 3

    def test_toxic_zero(self):
        creature = _make_creature()
        player = Player(name="Alice")
        result = apply_toxic_damage(creature, player, 0)
        assert result["poison_added"] == 0


class TestPoisonSBA:
    def test_poison_sba_in_game_state(self):
        """Verify that the game state checks poison as an SBA."""
        from mtg_engine.core.game_state import GameState
        state = GameState()
        player = Player(name="Alice")
        state.players.append(player)
        state.players.append(Player(name="Bob"))

        player.poison_counters = 10
        actions = state.check_state_based_actions()
        assert any("poison" in a.lower() for a in actions)
        assert player.lost
