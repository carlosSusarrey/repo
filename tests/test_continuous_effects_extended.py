"""Tests for extended continuous effects: Layers 3, 4, 5."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.continuous_effects import (
    ContinuousEffect,
    ContinuousEffectManager,
    Layer,
    PTSublayer,
    create_color_change_effect,
    create_text_change_effect,
    create_type_change_effect,
)
from mtg_engine.core.enums import CardType, Color, Zone
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost


def _make_creature(name="Bear", power=2, toughness=2):
    return Card(
        name=name,
        card_type=CardType.CREATURE,
        cost=ManaCost.parse("{1}{G}"),
        power=power,
        toughness=toughness,
        subtypes=["Bear"],
    )


def _make_instance(card=None, **kwargs):
    if card is None:
        card = _make_creature()
    return CardInstance(card=card, zone=Zone.BATTLEFIELD, **kwargs)


class TestTypeChangingEffects:
    def test_add_subtype(self):
        mgr = ContinuousEffectManager()
        instance = _make_instance()
        card_lookup = {instance.instance_id: instance}

        effect = create_type_change_effect(
            "src", instance.instance_id,
            add_subtypes=["Warrior"],
        )
        mgr.add_effect(effect)
        mgr.apply_all([instance], card_lookup)

        assert "Warrior" in instance.card.subtypes
        assert "Bear" in instance.card.subtypes  # Original preserved

    def test_remove_subtype(self):
        mgr = ContinuousEffectManager()
        instance = _make_instance()
        card_lookup = {instance.instance_id: instance}

        effect = create_type_change_effect(
            "src", instance.instance_id,
            remove_subtypes=["Bear"],
        )
        mgr.add_effect(effect)
        mgr.apply_all([instance], card_lookup)

        assert "Bear" not in instance.card.subtypes

    def test_change_card_type(self):
        mgr = ContinuousEffectManager()
        card = Card(
            name="Darksteel Citadel",
            card_type=CardType.ARTIFACT,
            subtypes=["Equipment"],
        )
        instance = _make_instance(card=card)
        card_lookup = {instance.instance_id: instance}

        effect = create_type_change_effect(
            "src", instance.instance_id,
            add_types=[CardType.CREATURE],
        )
        mgr.add_effect(effect)
        mgr.apply_all([instance], card_lookup)

        assert instance.card.card_type == CardType.CREATURE


class TestColorChangingEffects:
    def test_set_colors(self):
        mgr = ContinuousEffectManager()
        instance = _make_instance()
        card_lookup = {instance.instance_id: instance}

        effect = create_color_change_effect(
            "src", instance.instance_id,
            set_colors={Color.BLUE},
        )
        mgr.add_effect(effect)
        mgr.apply_all([instance], card_lookup)

        colors = getattr(instance, '_override_colors', None)
        assert colors is not None
        assert Color.BLUE in colors

    def test_add_color(self):
        mgr = ContinuousEffectManager()
        instance = _make_instance()
        card_lookup = {instance.instance_id: instance}

        effect = create_color_change_effect(
            "src", instance.instance_id,
            add_colors={Color.RED},
        )
        mgr.add_effect(effect)
        mgr.apply_all([instance], card_lookup)

        colors = getattr(instance, '_override_colors', set())
        assert Color.RED in colors

    def test_remove_color(self):
        mgr = ContinuousEffectManager()
        instance = _make_instance()
        card_lookup = {instance.instance_id: instance}

        # First set to multiple colors
        effect1 = create_color_change_effect(
            "src1", instance.instance_id,
            set_colors={Color.RED, Color.GREEN},
        )
        mgr.add_effect(effect1)

        # Then remove one
        effect2 = create_color_change_effect(
            "src2", instance.instance_id,
            remove_colors={Color.RED},
        )
        mgr.add_effect(effect2)
        mgr.apply_all([instance], card_lookup)

        colors = getattr(instance, '_override_colors', set())
        assert Color.GREEN in colors
        assert Color.RED not in colors


class TestTextChangingEffects:
    def test_text_replacement(self):
        mgr = ContinuousEffectManager()
        card = Card(
            name="Swampwalker",
            card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{B}"),
            power=2,
            toughness=2,
            rules_text="Swampwalk (This creature can't be blocked as long as defending player controls a Swamp.)",
        )
        instance = _make_instance(card=card)
        card_lookup = {instance.instance_id: instance}

        effect = create_text_change_effect(
            "src", instance.instance_id,
            replacements={"Swamp": "Island"},
        )
        mgr.add_effect(effect)
        mgr.apply_all([instance], card_lookup)

        assert "Island" in instance.card.rules_text
        assert "Swamp" not in instance.card.rules_text


class TestLayerOrdering:
    def test_type_before_ability(self):
        """Type-changing (Layer 4) should apply before ability-adding (Layer 6)."""
        mgr = ContinuousEffectManager()
        instance = _make_instance()
        card_lookup = {instance.instance_id: instance}

        # Layer 6: add flying
        ability_effect = ContinuousEffect(
            source_id="src1",
            layer=Layer.ABILITY,
            affected_ids=[instance.instance_id],
            add_keywords={Keyword.FLYING},
        )
        # Layer 4: change type (added first but should apply in layer order)
        type_effect = ContinuousEffect(
            source_id="src2",
            layer=Layer.TYPE,
            affected_ids=[instance.instance_id],
            add_subtypes=["Angel"],
        )

        # Add in reverse order to verify layer ordering
        mgr.add_effect(ability_effect)
        mgr.add_effect(type_effect)
        mgr.apply_all([instance], card_lookup)

        # Both should be applied
        assert "Angel" in instance.card.subtypes
        assert Keyword.FLYING in instance.keywords

    def test_all_permanents_filter(self):
        mgr = ContinuousEffectManager()
        creature = _make_instance()
        artifact = _make_instance(card=Card(
            name="Sol Ring", card_type=CardType.ARTIFACT,
        ))
        card_lookup = {
            creature.instance_id: creature,
            artifact.instance_id: artifact,
        }

        effect = ContinuousEffect(
            source_id="src",
            layer=Layer.COLOR,
            affect_filter="all_permanents",
            set_colors={Color.BLUE},
        )
        mgr.add_effect(effect)
        mgr.apply_all([creature, artifact], card_lookup)

        assert getattr(creature, '_override_colors', None) == {Color.BLUE}
        assert getattr(artifact, '_override_colors', None) == {Color.BLUE}
