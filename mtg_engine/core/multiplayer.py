"""Multiplayer support (3+ players, APNAP ordering).

CR 101.1: MTG supports 2+ players.
CR 101.4: APNAP order (Active Player, Non-Active Player) determines
  the order in which simultaneous choices are made.
CR 103.1: Multiplayer turn order goes clockwise from starting player.
CR 800+: Additional multiplayer rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MultiplayerState:
    """Tracks multiplayer-specific state."""
    player_count: int = 2
    turn_order: list[int] = field(default_factory=list)
    eliminated_players: set[int] = field(default_factory=set)
    # For range of influence (optional variant)
    range_of_influence: int | None = None  # None = unlimited

    def __post_init__(self) -> None:
        if not self.turn_order:
            self.turn_order = list(range(self.player_count))


def get_next_player(
    current_index: int,
    turn_order: list[int],
    eliminated: set[int],
) -> int:
    """Get the next active player in turn order, skipping eliminated players.

    Turn order goes clockwise (left in the list order).
    """
    if not turn_order:
        return 0

    current_pos = turn_order.index(current_index) if current_index in turn_order else 0
    count = len(turn_order)

    for offset in range(1, count + 1):
        next_pos = (current_pos + offset) % count
        next_player = turn_order[next_pos]
        if next_player not in eliminated:
            return next_player

    return current_index  # All eliminated (shouldn't happen)


def get_apnap_order(
    active_player: int,
    turn_order: list[int],
    eliminated: set[int],
) -> list[int]:
    """Get the APNAP ordering for simultaneous effects.

    CR 101.4: Active player's effects/choices go first, then
    non-active players in turn order.
    """
    result = [active_player]
    current = active_player

    while True:
        current = get_next_player(current, turn_order, eliminated)
        if current == active_player:
            break
        result.append(current)

    return result


def get_opponents(
    player_index: int,
    player_count: int,
    eliminated: set[int],
    range_of_influence: int | None = None,
    turn_order: list[int] | None = None,
) -> list[int]:
    """Get all opponents of a player.

    In multiplayer, all other non-eliminated players are opponents.
    With range of influence, only nearby players count.
    """
    opponents = []
    order = turn_order or list(range(player_count))

    if range_of_influence is None:
        # Unlimited range — everyone is an opponent
        for i in range(player_count):
            if i != player_index and i not in eliminated:
                opponents.append(i)
    else:
        # Limited range — only players within N seats
        pos = order.index(player_index) if player_index in order else 0
        active_order = [p for p in order if p not in eliminated]
        if player_index in active_order:
            my_pos = active_order.index(player_index)
            for offset in range(1, range_of_influence + 1):
                # Check both directions
                left = (my_pos - offset) % len(active_order)
                right = (my_pos + offset) % len(active_order)
                if active_order[left] != player_index:
                    opponents.append(active_order[left])
                if active_order[right] != player_index and active_order[right] not in opponents:
                    opponents.append(active_order[right])

    return opponents


def eliminate_player(
    state: MultiplayerState,
    player_index: int,
) -> list[str]:
    """Eliminate a player from the game.

    CR 800.4a: When a player leaves, all objects they own leave,
    effects they control end, etc.
    """
    actions = []
    state.eliminated_players.add(player_index)
    actions.append(f"Player {player_index} has been eliminated")
    return actions


def check_multiplayer_winner(
    state: MultiplayerState,
) -> int | None:
    """Check if only one player remains (they win).

    Returns the winning player index, or None if game continues.
    """
    remaining = [
        p for p in state.turn_order
        if p not in state.eliminated_players
    ]
    if len(remaining) == 1:
        return remaining[0]
    return None


def get_defending_players(
    attacker_player: int,
    state: MultiplayerState,
) -> list[int]:
    """Get valid defending players for an attacking player.

    In multiplayer, attackers can attack any opponent.
    """
    return get_opponents(
        attacker_player,
        state.player_count,
        state.eliminated_players,
        state.range_of_influence,
        state.turn_order,
    )


def setup_multiplayer(player_count: int) -> MultiplayerState:
    """Create a multiplayer state for N players."""
    return MultiplayerState(
        player_count=player_count,
        turn_order=list(range(player_count)),
    )
