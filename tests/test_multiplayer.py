"""Tests for multiplayer support."""

import pytest

from mtg_engine.core.multiplayer import (
    MultiplayerState,
    check_multiplayer_winner,
    eliminate_player,
    get_apnap_order,
    get_defending_players,
    get_next_player,
    get_opponents,
    setup_multiplayer,
)


class TestSetupMultiplayer:
    def test_setup_2_players(self):
        state = setup_multiplayer(2)
        assert state.player_count == 2
        assert state.turn_order == [0, 1]
        assert len(state.eliminated_players) == 0

    def test_setup_4_players(self):
        state = setup_multiplayer(4)
        assert state.player_count == 4
        assert state.turn_order == [0, 1, 2, 3]


class TestGetNextPlayer:
    def test_basic_next(self):
        order = [0, 1, 2, 3]
        assert get_next_player(0, order, set()) == 1
        assert get_next_player(1, order, set()) == 2
        assert get_next_player(3, order, set()) == 0  # Wraps

    def test_skip_eliminated(self):
        order = [0, 1, 2, 3]
        eliminated = {1}
        assert get_next_player(0, order, eliminated) == 2

    def test_skip_multiple_eliminated(self):
        order = [0, 1, 2, 3]
        eliminated = {1, 2}
        assert get_next_player(0, order, eliminated) == 3

    def test_wrap_with_eliminated(self):
        order = [0, 1, 2, 3]
        eliminated = {3}
        assert get_next_player(2, order, eliminated) == 0


class TestAPNAPOrder:
    def test_basic_apnap(self):
        order = get_apnap_order(0, [0, 1, 2, 3], set())
        assert order == [0, 1, 2, 3]

    def test_apnap_starts_with_active(self):
        order = get_apnap_order(2, [0, 1, 2, 3], set())
        assert order[0] == 2
        assert order == [2, 3, 0, 1]

    def test_apnap_with_eliminated(self):
        order = get_apnap_order(0, [0, 1, 2, 3], {2})
        assert 2 not in order
        assert order == [0, 1, 3]

    def test_apnap_two_players(self):
        order = get_apnap_order(0, [0, 1], set())
        assert order == [0, 1]


class TestGetOpponents:
    def test_two_player_opponents(self):
        opponents = get_opponents(0, 2, set())
        assert opponents == [1]

    def test_four_player_opponents(self):
        opponents = get_opponents(0, 4, set())
        assert set(opponents) == {1, 2, 3}

    def test_opponents_exclude_eliminated(self):
        opponents = get_opponents(0, 4, {2})
        assert 2 not in opponents
        assert set(opponents) == {1, 3}

    def test_range_of_influence(self):
        opponents = get_opponents(
            0, 4, set(),
            range_of_influence=1,
            turn_order=[0, 1, 2, 3],
        )
        # Only adjacent players
        assert 1 in opponents
        assert 3 in opponents
        assert 2 not in opponents


class TestEliminatePlayer:
    def test_eliminate(self):
        state = setup_multiplayer(4)
        actions = eliminate_player(state, 2)
        assert 2 in state.eliminated_players
        assert len(actions) > 0

    def test_eliminate_multiple(self):
        state = setup_multiplayer(4)
        eliminate_player(state, 1)
        eliminate_player(state, 3)
        assert state.eliminated_players == {1, 3}


class TestMultiplayerWinner:
    def test_no_winner_yet(self):
        state = setup_multiplayer(4)
        eliminate_player(state, 1)
        assert check_multiplayer_winner(state) is None

    def test_winner_when_one_remains(self):
        state = setup_multiplayer(4)
        eliminate_player(state, 0)
        eliminate_player(state, 1)
        eliminate_player(state, 3)
        winner = check_multiplayer_winner(state)
        assert winner == 2

    def test_two_player_winner(self):
        state = setup_multiplayer(2)
        eliminate_player(state, 0)
        winner = check_multiplayer_winner(state)
        assert winner == 1


class TestDefendingPlayers:
    def test_all_opponents_valid_targets(self):
        state = setup_multiplayer(4)
        defenders = get_defending_players(0, state)
        assert set(defenders) == {1, 2, 3}

    def test_eliminated_not_valid_targets(self):
        state = setup_multiplayer(4)
        eliminate_player(state, 2)
        defenders = get_defending_players(0, state)
        assert 2 not in defenders
        assert set(defenders) == {1, 3}
