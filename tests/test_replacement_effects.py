"""Tests for the replacement effects system."""

import pytest

from mtg_engine.core.replacement_effects import (
    ReplacementEffect,
    ReplacementEffectManager,
    ReplacementType,
    create_prevention_effect,
    create_etb_with_counters,
    create_etb_tapped,
    create_damage_redirect,
    create_life_gain_replacement,
    create_draw_replacement,
)


class TestReplacementEffectManager:
    def test_no_replacement_passes_through(self):
        mgr = ReplacementEffectManager()
        event = {"type": "damage", "amount": 3, "target": "player1"}
        result = mgr.check_replacement(ReplacementType.DAMAGE, event)
        assert result == event

    def test_prevent_damage(self):
        mgr = ReplacementEffectManager()
        effect = create_prevention_effect("src1")
        mgr.add_effect(effect)
        event = {"type": "damage", "amount": 5, "target": "player1"}
        result = mgr.check_replacement(ReplacementType.DAMAGE, event)
        assert result is None  # prevented

    def test_reduce_damage(self):
        mgr = ReplacementEffectManager()
        effect = create_prevention_effect("src1", prevent_amount=3)
        mgr.add_effect(effect)
        event = {"type": "damage", "amount": 5, "target": "player1"}
        result = mgr.check_replacement(ReplacementType.DAMAGE, event)
        assert result is not None
        assert result["amount"] == 2

    def test_reduce_damage_fully_prevented(self):
        mgr = ReplacementEffectManager()
        effect = create_prevention_effect("src1", prevent_amount=5)
        mgr.add_effect(effect)
        event = {"type": "damage", "amount": 3, "target": "player1"}
        result = mgr.check_replacement(ReplacementType.DAMAGE, event)
        assert result is None  # fully prevented

    def test_conditional_prevention(self):
        mgr = ReplacementEffectManager()
        # Only prevent damage to "player1"
        effect = create_prevention_effect(
            "src1",
            condition=lambda e: e.get("target") == "player1",
        )
        mgr.add_effect(effect)

        event1 = {"type": "damage", "amount": 3, "target": "player1"}
        assert mgr.check_replacement(ReplacementType.DAMAGE, event1) is None

        event2 = {"type": "damage", "amount": 3, "target": "player2"}
        result = mgr.check_replacement(ReplacementType.DAMAGE, event2)
        assert result is not None
        assert result["amount"] == 3

    def test_remove_effects(self):
        mgr = ReplacementEffectManager()
        effect = create_prevention_effect("src1")
        mgr.add_effect(effect)
        mgr.remove_effects_from("src1")
        event = {"type": "damage", "amount": 5, "target": "player1"}
        result = mgr.check_replacement(ReplacementType.DAMAGE, event)
        assert result is not None
        assert result["amount"] == 5


class TestETBReplacements:
    def test_etb_with_counters(self):
        mgr = ReplacementEffectManager()
        effect = create_etb_with_counters("card1", "+1/+1", 3)
        mgr.add_effect(effect)
        event = {"card_id": "card1"}
        result = mgr.check_replacement(ReplacementType.ENTER_BATTLEFIELD, event)
        assert result is not None
        assert result["counters"]["+1/+1"] == 3

    def test_etb_tapped(self):
        mgr = ReplacementEffectManager()
        effect = create_etb_tapped("card1")
        mgr.add_effect(effect)
        event = {"card_id": "card1"}
        result = mgr.check_replacement(ReplacementType.ENTER_BATTLEFIELD, event)
        assert result is not None
        assert result["enters_tapped"] is True

    def test_etb_condition_doesnt_apply(self):
        mgr = ReplacementEffectManager()
        effect = create_etb_with_counters("card1", "+1/+1", 3)
        mgr.add_effect(effect)
        event = {"card_id": "card2"}  # Different card
        result = mgr.check_replacement(ReplacementType.ENTER_BATTLEFIELD, event)
        assert result is not None
        assert "counters" not in result


class TestDamageRedirect:
    def test_redirect_damage(self):
        mgr = ReplacementEffectManager()
        effect = create_damage_redirect("src1", "planeswalker1")
        mgr.add_effect(effect)
        event = {"amount": 3, "target": "player1"}
        result = mgr.check_replacement(ReplacementType.DAMAGE, event)
        assert result is not None
        assert result["target"] == "planeswalker1"
        assert result["amount"] == 3


class TestLifeGainReplacement:
    def test_double_life_gain(self):
        mgr = ReplacementEffectManager()
        effect = create_life_gain_replacement(
            "src1",
            apply_fn=lambda e: {**e, "amount": e.get("amount", 0) * 2},
        )
        mgr.add_effect(effect)
        event = {"amount": 5, "player": "player1"}
        result = mgr.check_replacement(ReplacementType.LIFE_GAIN, event)
        assert result is not None
        assert result["amount"] == 10

    def test_prevent_life_gain(self):
        mgr = ReplacementEffectManager()
        effect = create_life_gain_replacement(
            "src1",
            apply_fn=lambda e: None,
        )
        mgr.add_effect(effect)
        event = {"amount": 5, "player": "player1"}
        result = mgr.check_replacement(ReplacementType.LIFE_GAIN, event)
        assert result is None


class TestDrawReplacement:
    def test_replace_draw_with_mill(self):
        mgr = ReplacementEffectManager()
        effect = create_draw_replacement(
            "src1",
            apply_fn=lambda e: {**e, "replaced_by": "mill"},
        )
        mgr.add_effect(effect)
        event = {"player": "player1"}
        result = mgr.check_replacement(ReplacementType.DRAW, event)
        assert result is not None
        assert result["replaced_by"] == "mill"


class TestSelfReplacementPriority:
    def test_self_replacement_applies_first(self):
        mgr = ReplacementEffectManager()
        # Self-replacement: enters with 2 counters
        self_effect = create_etb_with_counters("card1", "+1/+1", 2)
        mgr.add_effect(self_effect)

        # Other replacement: double counters
        other_effect = ReplacementEffect(
            source_id="doubler",
            replacement_type=ReplacementType.ENTER_BATTLEFIELD,
            apply=lambda e: {
                **e,
                "counters": {k: v * 2 for k, v in e.get("counters", {}).items()},
            },
        )
        mgr.add_effect(other_effect)

        event = {"card_id": "card1"}
        result = mgr.check_replacement(ReplacementType.ENTER_BATTLEFIELD, event)
        assert result is not None
        # Self-replacement adds 2, then doubler doubles to 4
        assert result["counters"]["+1/+1"] == 4
