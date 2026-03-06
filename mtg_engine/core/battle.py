"""Battle cards.

CR 310: Battles are permanents with defense counters.
Introduced in March of the Machine (2023).

Key rules:
- CR 310.1: Battles enter the battlefield with defense counters
- CR 310.4: A battle can be attacked (like a player or planeswalker)
- CR 310.7: When defense reaches 0, battle is exiled and its
  controller may cast the transformed back face (if it has one)
- CR 310.11: Siege is a battle subtype; opponent is assigned as
  the battle's protector when it enters
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone


@dataclass
class BattleState:
    """Tracks battle-specific state."""
    defense: int = 0
    protector_index: int = 0  # Player who protects this battle
    is_siege: bool = False


def setup_battle(
    card_instance: CardInstance,
    defense: int,
    protector_index: int,
    is_siege: bool = True,
) -> None:
    """Set up a card instance as a battle.

    CR 310.1: Enters with defense counters equal to its printed defense.
    CR 310.11 (Siege): When a Siege enters, its controller chooses
    an opponent to be the battle's protector.
    """
    state = BattleState(
        defense=defense,
        protector_index=protector_index,
        is_siege=is_siege,
    )
    card_instance._battle_state = state  # type: ignore[attr-defined]
    card_instance.counters["defense"] = defense


def get_defense(card_instance: CardInstance) -> int:
    """Get current defense counters on a battle."""
    return card_instance.counters.get("defense", 0)


def deal_damage_to_battle(
    card_instance: CardInstance,
    amount: int,
) -> int:
    """Deal damage to a battle (removes defense counters).

    CR 310.4c: Damage dealt to a battle removes that many defense counters.
    Returns remaining defense.
    """
    if amount <= 0:
        return get_defense(card_instance)

    current = get_defense(card_instance)
    new_defense = max(0, current - amount)
    card_instance.counters["defense"] = new_defense
    return new_defense


def is_battle_defeated(card_instance: CardInstance) -> bool:
    """Check if a battle has been defeated (0 defense counters).

    CR 310.7 (SBA): When a battle's defense reaches 0, it's exiled.
    """
    state = getattr(card_instance, '_battle_state', None)
    if state is None:
        return False
    return get_defense(card_instance) <= 0


def get_protector(card_instance: CardInstance) -> int | None:
    """Get the protector player index for a battle."""
    state = getattr(card_instance, '_battle_state', None)
    if state is None:
        return None
    return state.protector_index


def can_attack_battle(
    attacker: CardInstance,
    battle: CardInstance,
) -> bool:
    """Check if a creature can attack a battle.

    CR 310.4: A battle can be attacked by creatures controlled
    by non-protector players.
    """
    state = getattr(battle, '_battle_state', None)
    if state is None:
        return False
    if battle.zone != Zone.BATTLEFIELD:
        return False
    # Attacker must not be controlled by the protector
    return attacker.controller_index != state.protector_index


def can_block_for_battle(
    blocker: CardInstance,
    battle: CardInstance,
) -> bool:
    """Check if a creature can block for a battle.

    CR 310.4b: Only the protector's creatures can block
    creatures attacking this battle.
    """
    state = getattr(battle, '_battle_state', None)
    if state is None:
        return False
    return blocker.controller_index == state.protector_index


def is_battle(card_instance: CardInstance) -> bool:
    """Check if a card instance is a battle."""
    return getattr(card_instance, '_battle_state', None) is not None


def is_siege(card_instance: CardInstance) -> bool:
    """Check if a card instance is a siege battle."""
    state = getattr(card_instance, '_battle_state', None)
    return state is not None and state.is_siege
