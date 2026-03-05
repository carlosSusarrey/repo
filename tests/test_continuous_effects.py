"""Tests for the 7-layer continuous effects system."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.continuous_effects import (
    ContinuousEffect,
    ContinuousEffectManager,
    Layer,
    PTSublayer,
    create_anthem_effect,
    create_control_change_effect,
    create_keyword_grant_effect,
    create_pump_effect,
)
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.keywords import Keyword


def _make_creature(name="Bear", power=2, toughness=2, owner=0):
    card = Card(name=name, card_type=CardType.CREATURE, power=power, toughness=toughness)
    inst = CardInstance(card=card, zone=Zone.BATTLEFIELD, owner_index=owner, controller_index=owner)
    return inst


class TestContinuousEffectManager:
    def test_add_and_remove_effects(self):
        mgr = ContinuousEffectManager()
        effect = create_pump_effect("source1", "target1", 2, 2)
        mgr.add_effect(effect)
        assert len(mgr.effects) == 1

        mgr.remove_effects_from("source1")
        assert len(mgr.effects) == 0

    def test_remove_end_of_turn_effects(self):
        mgr = ContinuousEffectManager()
        e1 = create_pump_effect("s1", "t1", 2, 2, "end_of_turn")
        e2 = create_pump_effect("s2", "t2", 1, 1, "permanent")
        mgr.add_effect(e1)
        mgr.add_effect(e2)
        assert len(mgr.effects) == 2

        mgr.remove_end_of_turn_effects()
        assert len(mgr.effects) == 1
        assert mgr.effects[0].source_id == "s2"


class TestPumpEffect:
    def test_create_pump_effect(self):
        effect = create_pump_effect("source", "target", 3, 3)
        assert effect.layer == Layer.POWER_TOUGHNESS
        assert effect.pt_sublayer == PTSublayer.MODIFY
        assert effect.power_mod == 3
        assert effect.toughness_mod == 3
        assert effect.duration == "end_of_turn"

    def test_apply_pump_to_creature(self):
        bear = _make_creature()
        mgr = ContinuousEffectManager()
        effect = create_pump_effect("source", bear.instance_id, 3, 3)
        mgr.add_effect(effect)

        lookup = {bear.instance_id: bear}
        mgr.apply_all([bear], lookup)

        assert bear.temp_power_mod == 3
        assert bear.temp_toughness_mod == 3
        assert bear.current_power == 5  # 2 + 3
        assert bear.current_toughness == 5


class TestKeywordGrantEffect:
    def test_grant_keyword(self):
        bear = _make_creature()
        mgr = ContinuousEffectManager()
        effect = create_keyword_grant_effect(
            "source", bear.instance_id, {Keyword.FLYING}
        )
        mgr.add_effect(effect)

        lookup = {bear.instance_id: bear}
        mgr.apply_all([bear], lookup)

        assert Keyword.FLYING in bear.keywords


class TestAnthemEffect:
    def test_anthem_boosts_your_creatures(self):
        source = _make_creature(name="Lord", owner=0)
        bear1 = _make_creature(name="Bear1", owner=0)
        bear2 = _make_creature(name="Bear2", owner=0)
        opp_bear = _make_creature(name="OppBear", owner=1)

        mgr = ContinuousEffectManager()
        effect = create_anthem_effect(source.instance_id, 1, 1, "your_creatures")
        mgr.add_effect(effect)

        all_cards = [source, bear1, bear2, opp_bear]
        lookup = {c.instance_id: c for c in all_cards}
        mgr.apply_all(all_cards, lookup)

        # Your creatures get +1/+1
        assert bear1.current_power == 3
        assert bear1.current_toughness == 3
        assert bear2.current_power == 3
        # Source also gets boosted (it's your creature)
        assert source.current_power == 3
        # Opponent's creature doesn't
        assert opp_bear.current_power == 2

    def test_anthem_all_creatures(self):
        source = _make_creature(name="Anthem", owner=0)
        bear = _make_creature(name="Bear", owner=0)
        opp_bear = _make_creature(name="OppBear", owner=1)

        mgr = ContinuousEffectManager()
        effect = create_anthem_effect(source.instance_id, 1, 1, "all_creatures")
        mgr.add_effect(effect)

        all_cards = [source, bear, opp_bear]
        lookup = {c.instance_id: c for c in all_cards}
        mgr.apply_all(all_cards, lookup)

        assert bear.current_power == 3
        assert opp_bear.current_power == 3


class TestControlChangeEffect:
    def test_control_change(self):
        creature = _make_creature(owner=0)
        assert creature.controller_index == 0

        mgr = ContinuousEffectManager()
        effect = create_control_change_effect("source", creature.instance_id, 1)
        mgr.add_effect(effect)

        lookup = {creature.instance_id: creature}
        mgr.apply_all([creature], lookup)

        assert creature.controller_index == 1


class TestLayerOrdering:
    def test_effects_applied_in_layer_order(self):
        """Control change (layer 2) should happen before P/T mod (layer 7)."""
        creature = _make_creature(owner=0)

        mgr = ContinuousEffectManager()
        # Add PT mod first, then control change - should still apply in correct order
        pt_effect = create_pump_effect("s1", creature.instance_id, 2, 2)
        control_effect = create_control_change_effect("s2", creature.instance_id, 1)
        mgr.add_effect(pt_effect)
        mgr.add_effect(control_effect)

        lookup = {creature.instance_id: creature}
        mgr.apply_all([creature], lookup)

        # Control changes in layer 2, before PT in layer 7
        assert creature.controller_index == 1
        assert creature.current_power == 4  # 2 + 2

    def test_timestamp_ordering_within_layer(self):
        """Within the same layer, earlier effects apply first."""
        creature = _make_creature(owner=0)

        mgr = ContinuousEffectManager()
        e1 = create_pump_effect("s1", creature.instance_id, 1, 1)
        e2 = create_pump_effect("s2", creature.instance_id, 2, 2)
        mgr.add_effect(e1)
        mgr.add_effect(e2)

        lookup = {creature.instance_id: creature}
        mgr.apply_all([creature], lookup)

        # Both should apply: +1+2 = +3 total
        assert creature.current_power == 5  # 2 + 1 + 2
        assert creature.current_toughness == 5
