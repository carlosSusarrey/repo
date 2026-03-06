"""Tests for state-based actions."""

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, SuperType, Zone
from mtg_engine.core.game_state import GameState
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost
from mtg_engine.core.player import Player


def _make_state():
    state = GameState()
    state.players = [Player(name="Alice"), Player(name="Bob")]
    return state


class TestIndestructible:
    def test_indestructible_survives_lethal_damage(self):
        state = _make_state()
        card = Card(
            name="Darksteel Colossus", card_type=CardType.CREATURE,
            power=11, toughness=11, keywords={Keyword.INDESTRUCTIBLE},
        )
        inst = CardInstance(card=card, zone=Zone.BATTLEFIELD, owner_index=0)
        inst.damage_marked = 20
        state.cards.append(inst)

        actions = state.check_state_based_actions()
        # Should survive
        assert inst.zone == Zone.BATTLEFIELD

    def test_zero_toughness_still_dies(self):
        """Indestructible doesn't save from 0 toughness."""
        state = _make_state()
        card = Card(
            name="Thing", card_type=CardType.CREATURE,
            power=1, toughness=1, keywords={Keyword.INDESTRUCTIBLE},
        )
        inst = CardInstance(card=card, zone=Zone.BATTLEFIELD, owner_index=0)
        inst.counters["-1/-1"] = 1  # toughness becomes 0
        state.cards.append(inst)

        state.check_state_based_actions()
        assert inst.zone == Zone.GRAVEYARD


class TestLegendRule:
    def test_legend_rule_keeps_newest(self):
        state = _make_state()
        card_def = Card(
            name="Jace", card_type=CardType.PLANESWALKER,
            supertypes=[SuperType.LEGENDARY], loyalty=3,
        )
        inst1 = CardInstance(card=card_def, zone=Zone.BATTLEFIELD,
                             owner_index=0, controller_index=0)
        inst2 = CardInstance(card=card_def, zone=Zone.BATTLEFIELD,
                             owner_index=0, controller_index=0)
        # Set loyalty counters
        inst1.counters["loyalty"] = 3
        inst2.counters["loyalty"] = 3
        state.cards.extend([inst1, inst2])

        actions = state.check_state_based_actions()
        battlefield = state.get_battlefield(0)
        # Should keep only one
        legendary_on_bf = [c for c in battlefield if c.name == "Jace"]
        assert len(legendary_on_bf) == 1

    def test_different_names_no_conflict(self):
        state = _make_state()
        card1 = Card(name="Jace", card_type=CardType.CREATURE,
                     supertypes=[SuperType.LEGENDARY], power=2, toughness=2)
        card2 = Card(name="Chandra", card_type=CardType.CREATURE,
                     supertypes=[SuperType.LEGENDARY], power=3, toughness=3)
        inst1 = CardInstance(card=card1, zone=Zone.BATTLEFIELD, owner_index=0, controller_index=0)
        inst2 = CardInstance(card=card2, zone=Zone.BATTLEFIELD, owner_index=0, controller_index=0)
        state.cards.extend([inst1, inst2])

        actions = state.check_state_based_actions()
        assert inst1.zone == Zone.BATTLEFIELD
        assert inst2.zone == Zone.BATTLEFIELD


class TestCounterCancellation:
    def test_counters_cancel(self):
        state = _make_state()
        card = Card(name="Bear", card_type=CardType.CREATURE, power=2, toughness=2)
        inst = CardInstance(card=card, zone=Zone.BATTLEFIELD, owner_index=0)
        inst.counters["+1/+1"] = 3
        inst.counters["-1/-1"] = 2
        state.cards.append(inst)

        state.check_state_based_actions()
        assert inst.counters.get("+1/+1", 0) == 1
        assert "-1/-1" not in inst.counters
