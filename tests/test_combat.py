"""Tests for the combat system."""

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.combat import (
    CombatState, assign_combat_damage, validate_attackers,
    has_first_strike_creatures, get_first_strike_damage, get_regular_damage,
)
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.game import Game
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost


def _creature(name, power, toughness, keywords=None, cost="", owner=0):
    card = Card(
        name=name, card_type=CardType.CREATURE,
        cost=ManaCost.parse(cost) if cost else ManaCost(),
        power=power, toughness=toughness,
        keywords=keywords or set(),
    )
    inst = CardInstance(
        card=card, zone=Zone.BATTLEFIELD,
        owner_index=owner, controller_index=owner,
    )
    return inst


class TestCombatState:
    def test_declare_attacker(self):
        cs = CombatState()
        cs.declare_attacker("a1", 1)
        assert cs.has_attackers
        assert cs.is_unblocked("a1")

    def test_declare_blocker(self):
        cs = CombatState()
        cs.declare_attacker("a1", 1)
        cs.declare_blocker("b1", "a1")
        assert cs.is_blocked("a1")
        assert not cs.is_unblocked("a1")

    def test_clear(self):
        cs = CombatState()
        cs.declare_attacker("a1", 1)
        cs.clear()
        assert not cs.has_attackers


class TestDamageAssignment:
    def test_unblocked_damage_to_player(self):
        attacker = _creature("Bear", 2, 2)
        cs = CombatState()
        cs.declare_attacker(attacker.instance_id, 1)

        lookup = {attacker.instance_id: attacker}
        assignments = assign_combat_damage(cs, lookup)

        assert len(assignments) == 1
        assert assignments[0].target_id == "player:1"
        assert assignments[0].amount == 2

    def test_blocked_damage(self):
        attacker = _creature("Bear", 2, 2, owner=0)
        blocker = _creature("Wall", 0, 4, owner=1)

        cs = CombatState()
        cs.declare_attacker(attacker.instance_id, 1)
        cs.declare_blocker(blocker.instance_id, attacker.instance_id)

        lookup = {attacker.instance_id: attacker, blocker.instance_id: blocker}
        assignments = assign_combat_damage(cs, lookup)

        # Attacker deals 2 to blocker, blocker deals 0 to attacker
        creature_dmg = [a for a in assignments if not a.target_id.startswith("player:")]
        assert any(a.source_id == attacker.instance_id and a.amount == 2 for a in creature_dmg)

    def test_trample_excess(self):
        attacker = _creature("Trampler", 5, 5, {Keyword.TRAMPLE})
        blocker = _creature("Chump", 1, 1)

        cs = CombatState()
        cs.declare_attacker(attacker.instance_id, 1)
        cs.declare_blocker(blocker.instance_id, attacker.instance_id)

        lookup = {attacker.instance_id: attacker, blocker.instance_id: blocker}
        assignments = assign_combat_damage(cs, lookup)

        player_dmg = [a for a in assignments if a.target_id == "player:1"]
        blocker_dmg = [a for a in assignments if a.target_id == blocker.instance_id]

        # 1 damage to blocker (lethal), 4 trample to player
        assert blocker_dmg[0].amount == 1
        assert player_dmg[0].amount == 4

    def test_deathtouch_trample(self):
        attacker = _creature("DT Trampler", 5, 5, {Keyword.DEATHTOUCH, Keyword.TRAMPLE})
        blocker = _creature("Big Wall", 0, 10)

        cs = CombatState()
        cs.declare_attacker(attacker.instance_id, 1)
        cs.declare_blocker(blocker.instance_id, attacker.instance_id)

        lookup = {attacker.instance_id: attacker, blocker.instance_id: blocker}
        assignments = assign_combat_damage(cs, lookup)

        player_dmg = [a for a in assignments if a.target_id == "player:1"]
        blocker_dmg = [a for a in assignments if a.target_id == blocker.instance_id]

        # Deathtouch: only 1 needed for lethal, 4 tramples through
        assert blocker_dmg[0].amount == 1
        assert player_dmg[0].amount == 4

    def test_lifelink_flag(self):
        attacker = _creature("Lifelinker", 3, 3, {Keyword.LIFELINK})
        cs = CombatState()
        cs.declare_attacker(attacker.instance_id, 1)

        lookup = {attacker.instance_id: attacker}
        assignments = assign_combat_damage(cs, lookup)

        assert assignments[0].has_lifelink


class TestFirstStrike:
    def test_has_first_strike(self):
        attacker = _creature("FS", 2, 2, {Keyword.FIRST_STRIKE})
        cs = CombatState()
        cs.declare_attacker(attacker.instance_id, 1)

        lookup = {attacker.instance_id: attacker}
        assert has_first_strike_creatures(cs, lookup)

    def test_first_strike_damage(self):
        attacker = _creature("FS", 2, 2, {Keyword.FIRST_STRIKE})
        cs = CombatState()
        cs.declare_attacker(attacker.instance_id, 1)

        lookup = {attacker.instance_id: attacker}
        fs_dmg = get_first_strike_damage(cs, lookup)
        assert len(fs_dmg) == 1
        assert fs_dmg[0].amount == 2

    def test_regular_damage_excludes_first_strike(self):
        attacker = _creature("FS", 2, 2, {Keyword.FIRST_STRIKE})
        cs = CombatState()
        cs.declare_attacker(attacker.instance_id, 1)

        lookup = {attacker.instance_id: attacker}
        reg_dmg = get_regular_damage(cs, lookup)
        # First strike only creature should NOT deal regular damage
        assert len(reg_dmg) == 0

    def test_double_strike_deals_both(self):
        attacker = _creature("DS", 3, 3, {Keyword.DOUBLE_STRIKE})
        cs = CombatState()
        cs.declare_attacker(attacker.instance_id, 1)

        lookup = {attacker.instance_id: attacker}
        fs_dmg = get_first_strike_damage(cs, lookup)
        reg_dmg = get_regular_damage(cs, lookup)

        assert len(fs_dmg) == 1 and fs_dmg[0].amount == 3
        assert len(reg_dmg) == 1 and reg_dmg[0].amount == 3


class TestGameCombat:
    def _make_combat_game(self):
        """Create a game with creatures on the battlefield."""
        land = Card(name="Land", card_type=CardType.LAND)
        game = Game(["Alice", "Bob"], [[land] * 40, [land] * 40])

        # Put creatures directly on battlefield
        bear = Card(name="Bear", card_type=CardType.CREATURE,
                    power=2, toughness=2)
        angel = Card(name="Angel", card_type=CardType.CREATURE,
                     power=4, toughness=4,
                     keywords={Keyword.FLYING, Keyword.VIGILANCE})

        bear_inst = CardInstance(card=bear, zone=Zone.BATTLEFIELD,
                                owner_index=0, controller_index=0)
        angel_inst = CardInstance(card=angel, zone=Zone.BATTLEFIELD,
                                 owner_index=1, controller_index=1)

        game.state.cards.extend([bear_inst, angel_inst])
        return game, bear_inst, angel_inst

    def test_declare_attackers(self):
        game, bear, angel = self._make_combat_game()
        valid = game.declare_attackers([bear.instance_id])
        assert bear.instance_id in valid
        assert bear.tapped  # Should be tapped (no vigilance)

    def test_vigilance_no_tap(self):
        game, bear, angel = self._make_combat_game()
        # Angel is player 1's creature; switch active player to 1
        game.state.active_player_index = 1
        valid = game.declare_attackers([angel.instance_id])
        assert angel.instance_id in valid
        assert not angel.tapped  # Vigilance!

    def test_declare_blockers(self):
        game, bear, angel = self._make_combat_game()
        game.declare_attackers([bear.instance_id])
        blocks = game.declare_blockers({angel.instance_id: bear.instance_id})

        # Angel can't block bear (bear doesn't have flying) — wait, that's wrong.
        # Angel CAN block bear. Only flying ATTACKERS need flying/reach BLOCKERS.
        assert angel.instance_id in blocks

    def test_resolve_combat_damage(self):
        game, bear, angel = self._make_combat_game()
        game.declare_attackers([bear.instance_id])
        game.declare_blockers({angel.instance_id: bear.instance_id})
        log = game.resolve_combat_damage()

        # Bear (2/2) attacks, Angel (4/4) blocks
        # Angel deals 4 to Bear — lethal, so SBAs kill Bear (damage reset on zone change)
        # Bear deals 2 to Angel — survives
        assert angel.damage_marked == 2
        # Bear should be in graveyard (killed by SBAs after lethal damage)
        assert bear.zone == Zone.GRAVEYARD
