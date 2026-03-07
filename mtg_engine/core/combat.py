"""Combat system — declaring attackers, blockers, and resolving damage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mtg_engine.core.card import CardInstance
from mtg_engine.core.keywords import Keyword, can_block as kw_can_block


@dataclass
class CombatState:
    """Tracks the state of combat for a single combat phase."""

    # attacker instance_id -> defending player index (or planeswalker id)
    attackers: dict[str, int] = field(default_factory=dict)
    # blocker instance_id -> list of attacker instance_ids it's blocking
    blockers: dict[str, list[str]] = field(default_factory=dict)
    # attacker instance_id -> list of blocker instance_ids blocking it
    blocked_by: dict[str, list[str]] = field(default_factory=dict)
    # Track which attackers were blocked (even if blockers later removed)
    was_blocked: set[str] = field(default_factory=set)
    # First strike damage already dealt
    first_strike_dealt: bool = False

    def clear(self) -> None:
        self.attackers.clear()
        self.blockers.clear()
        self.blocked_by.clear()
        self.was_blocked.clear()
        self.first_strike_dealt = False

    def declare_attacker(self, attacker_id: str, defending_player: int) -> None:
        self.attackers[attacker_id] = defending_player
        self.blocked_by[attacker_id] = []

    def declare_blocker(self, blocker_id: str, attacker_id: str) -> bool:
        """Declare a blocker for an attacker. Returns True if valid."""
        if attacker_id not in self.attackers:
            return False
        if blocker_id not in self.blockers:
            self.blockers[blocker_id] = []
        self.blockers[blocker_id].append(attacker_id)
        self.blocked_by[attacker_id].append(blocker_id)
        self.was_blocked.add(attacker_id)
        return True

    def is_blocked(self, attacker_id: str) -> bool:
        return attacker_id in self.was_blocked

    def is_unblocked(self, attacker_id: str) -> bool:
        return attacker_id in self.attackers and attacker_id not in self.was_blocked

    @property
    def has_attackers(self) -> bool:
        return len(self.attackers) > 0


def validate_attackers(
    creatures: list[CardInstance],
    proposed_attackers: list[str],
) -> list[str]:
    """Return list of valid attacker IDs from the proposed list."""
    valid = []
    creature_map = {c.instance_id: c for c in creatures}
    for aid in proposed_attackers:
        creature = creature_map.get(aid)
        if creature and creature.can_attack():
            valid.append(aid)
    return valid


def validate_blockers(
    attacker_map: dict[str, CardInstance],
    blocker_map: dict[str, CardInstance],
    proposed_blocks: dict[str, str],  # blocker_id -> attacker_id
    combat_state: CombatState,
) -> dict[str, str]:
    """Validate proposed blocks. Returns valid blocker_id -> attacker_id mapping."""
    valid = {}
    for blocker_id, attacker_id in proposed_blocks.items():
        blocker = blocker_map.get(blocker_id)
        attacker = attacker_map.get(attacker_id)
        if not blocker or not attacker:
            continue
        if not blocker.can_block():
            continue
        if attacker_id not in combat_state.attackers:
            continue

        # Check keyword-based blocking restrictions
        if not kw_can_block(
            attacker.keywords, blocker.keywords,
            attacker.card.colors, blocker.card.colors,
            attacker_keyword_params=attacker.card.keyword_params,
            blocker_card_types=blocker.card.card_types,
        ):
            continue

        valid[blocker_id] = attacker_id

    return valid


def validate_menace(
    combat_state: CombatState,
    attacker_map: dict[str, CardInstance],
) -> list[str]:
    """Return list of attacker IDs that violate menace (blocked by < 2 creatures).

    These attackers should be treated as unblocked.
    """
    violations = []
    for attacker_id, blocker_ids in combat_state.blocked_by.items():
        attacker = attacker_map.get(attacker_id)
        if attacker and attacker.has_keyword(Keyword.MENACE):
            if len(blocker_ids) < 2 and len(blocker_ids) > 0:
                violations.append(attacker_id)
    return violations


@dataclass
class DamageAssignment:
    """Result of combat damage assignment for one creature."""
    source_id: str
    target_id: str  # creature instance_id or "player:<index>"
    amount: int
    is_combat: bool = True
    has_deathtouch: bool = False
    has_lifelink: bool = False
    has_trample: bool = False


def assign_combat_damage(
    combat_state: CombatState,
    card_lookup: dict[str, CardInstance],
) -> list[DamageAssignment]:
    """Assign combat damage for all attackers.

    Returns a list of DamageAssignment objects to be applied.
    """
    assignments: list[DamageAssignment] = []

    for attacker_id, defending_player in combat_state.attackers.items():
        attacker = card_lookup.get(attacker_id)
        if not attacker or attacker.current_power is None or attacker.current_power <= 0:
            continue

        power = attacker.current_power
        has_deathtouch = attacker.has_keyword(Keyword.DEATHTOUCH)
        has_lifelink = attacker.has_keyword(Keyword.LIFELINK)
        has_trample = attacker.has_keyword(Keyword.TRAMPLE)

        blocker_ids = combat_state.blocked_by.get(attacker_id, [])

        if not combat_state.is_blocked(attacker_id):
            # Unblocked: all damage to defending player
            assignments.append(DamageAssignment(
                source_id=attacker_id,
                target_id=f"player:{defending_player}",
                amount=power,
                has_deathtouch=has_deathtouch,
                has_lifelink=has_lifelink,
            ))
        elif not blocker_ids:
            # Was blocked but blockers removed — no damage dealt
            # (unless trample, in which case all goes to player)
            if has_trample:
                assignments.append(DamageAssignment(
                    source_id=attacker_id,
                    target_id=f"player:{defending_player}",
                    amount=power,
                    has_deathtouch=has_deathtouch,
                    has_lifelink=has_lifelink,
                    has_trample=True,
                ))
        else:
            # Blocked: distribute damage among blockers
            remaining_power = power
            for i, blocker_id in enumerate(blocker_ids):
                blocker = card_lookup.get(blocker_id)
                if not blocker or blocker.current_toughness is None:
                    continue

                is_last = (i == len(blocker_ids) - 1)

                if has_deathtouch:
                    # Deathtouch: 1 damage is lethal for assignment
                    lethal = max(1, 1)  # 1 damage is enough
                else:
                    lethal = max(0, blocker.current_toughness - blocker.damage_marked)

                if is_last and not has_trample:
                    # Last blocker gets all remaining
                    damage_to_blocker = remaining_power
                else:
                    damage_to_blocker = min(lethal, remaining_power)

                if damage_to_blocker > 0:
                    assignments.append(DamageAssignment(
                        source_id=attacker_id,
                        target_id=blocker_id,
                        amount=damage_to_blocker,
                        has_deathtouch=has_deathtouch,
                        has_lifelink=has_lifelink,
                    ))
                    remaining_power -= damage_to_blocker

            # Trample: excess goes to defending player
            if has_trample and remaining_power > 0:
                assignments.append(DamageAssignment(
                    source_id=attacker_id,
                    target_id=f"player:{defending_player}",
                    amount=remaining_power,
                    has_deathtouch=has_deathtouch,
                    has_lifelink=has_lifelink,
                    has_trample=True,
                ))

    # Blockers deal damage to the attacker they're blocking
    for blocker_id, attacker_ids in combat_state.blockers.items():
        blocker = card_lookup.get(blocker_id)
        if not blocker or blocker.current_power is None or blocker.current_power <= 0:
            continue
        # Blocker deals damage to first attacker it's blocking
        if attacker_ids:
            assignments.append(DamageAssignment(
                source_id=blocker_id,
                target_id=attacker_ids[0],
                amount=blocker.current_power,
                has_deathtouch=blocker.has_keyword(Keyword.DEATHTOUCH),
                has_lifelink=blocker.has_keyword(Keyword.LIFELINK),
            ))

    return assignments


def has_first_strike_creatures(
    combat_state: CombatState,
    card_lookup: dict[str, CardInstance],
) -> bool:
    """Check if any creature in combat has first strike or double strike."""
    all_ids = set(combat_state.attackers.keys()) | set(combat_state.blockers.keys())
    for cid in all_ids:
        card = card_lookup.get(cid)
        if card and (card.has_keyword(Keyword.FIRST_STRIKE) or card.has_keyword(Keyword.DOUBLE_STRIKE)):
            return True
    return False


def get_first_strike_damage(
    combat_state: CombatState,
    card_lookup: dict[str, CardInstance],
) -> list[DamageAssignment]:
    """Get damage assignments for the first strike damage step.

    Only creatures with first strike or double strike deal damage.
    """
    # Filter to only first/double strikers
    fs_attackers = {}
    for aid, dp in combat_state.attackers.items():
        card = card_lookup.get(aid)
        if card and (card.has_keyword(Keyword.FIRST_STRIKE) or card.has_keyword(Keyword.DOUBLE_STRIKE)):
            fs_attackers[aid] = dp

    fs_blockers = {}
    for bid, aids in combat_state.blockers.items():
        card = card_lookup.get(bid)
        if card and (card.has_keyword(Keyword.FIRST_STRIKE) or card.has_keyword(Keyword.DOUBLE_STRIKE)):
            fs_blockers[bid] = aids

    # Create a temporary combat state for just first strikers
    fs_combat = CombatState()
    fs_combat.attackers = fs_attackers
    fs_combat.blockers = fs_blockers
    fs_combat.blocked_by = {
        aid: [bid for bid in bids if bid in fs_blockers]
        for aid, bids in combat_state.blocked_by.items()
        if aid in fs_attackers
    }
    fs_combat.was_blocked = combat_state.was_blocked & set(fs_attackers.keys())

    return assign_combat_damage(fs_combat, card_lookup)


def get_regular_damage(
    combat_state: CombatState,
    card_lookup: dict[str, CardInstance],
) -> list[DamageAssignment]:
    """Get damage for the regular damage step.

    Excludes creatures with first strike (but includes double strike).
    """
    reg_attackers = {}
    for aid, dp in combat_state.attackers.items():
        card = card_lookup.get(aid)
        if card:
            has_fs = card.has_keyword(Keyword.FIRST_STRIKE)
            has_ds = card.has_keyword(Keyword.DOUBLE_STRIKE)
            # Include if: no first strike, OR has double strike
            if not has_fs or has_ds:
                reg_attackers[aid] = dp

    reg_blockers = {}
    for bid, aids in combat_state.blockers.items():
        card = card_lookup.get(bid)
        if card:
            has_fs = card.has_keyword(Keyword.FIRST_STRIKE)
            has_ds = card.has_keyword(Keyword.DOUBLE_STRIKE)
            if not has_fs or has_ds:
                reg_blockers[bid] = aids

    reg_combat = CombatState()
    reg_combat.attackers = reg_attackers
    reg_combat.blockers = reg_blockers
    reg_combat.blocked_by = {
        aid: [bid for bid in bids if bid in reg_blockers]
        for aid, bids in combat_state.blocked_by.items()
        if aid in reg_attackers
    }
    reg_combat.was_blocked = combat_state.was_blocked & set(reg_attackers.keys())

    return assign_combat_damage(reg_combat, card_lookup)
