"""Tests for the copy effects system."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.copy_effects import (
    CopyEffect,
    CopyEffectManager,
    apply_copy_effect,
    create_token_copy,
    get_copiable_values,
)
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost


def _make_creature(name="Bear", power=2, toughness=2, cost="1G",
                   keywords=None, subtypes=None):
    return Card(
        name=name,
        card_type=CardType.CREATURE,
        cost=ManaCost.parse(cost),
        power=power,
        toughness=toughness,
        keywords=keywords or set(),
        subtypes=subtypes or [],
    )


class TestGetCopiableValues:
    def test_copies_basic_values(self):
        card = _make_creature("Grizzly Bears", 2, 2, "1G", subtypes=["Bear"])
        values = get_copiable_values(card)
        assert values["name"] == "Grizzly Bears"
        assert values["power"] == 2
        assert values["toughness"] == 2
        assert values["card_type"] == CardType.CREATURE
        assert "Bear" in values["subtypes"]

    def test_copies_keywords(self):
        card = _make_creature(keywords={Keyword.FLYING, Keyword.LIFELINK})
        values = get_copiable_values(card)
        assert Keyword.FLYING in values["keywords"]
        assert Keyword.LIFELINK in values["keywords"]


class TestApplyCopyEffect:
    def test_clone_copies_creature(self):
        original = _make_creature("Dragon", 5, 5, "4RR", {Keyword.FLYING})
        clone_card = _make_creature("Clone", 0, 0, "3U")
        clone_instance = CardInstance(card=clone_card, zone=Zone.BATTLEFIELD)

        apply_copy_effect(clone_instance, original)

        assert clone_instance.card.name == "Dragon"
        assert clone_instance.card.power == 5
        assert clone_instance.card.toughness == 5
        assert Keyword.FLYING in clone_instance.card.keywords

    def test_clone_with_except_name(self):
        original = _make_creature("Dragon", 5, 5, "4RR")
        clone_card = _make_creature("Clever Impersonator", 0, 0, "2UU")
        clone_instance = CardInstance(card=clone_card, zone=Zone.BATTLEFIELD)

        effect = CopyEffect(
            source_id=clone_instance.instance_id,
            original_id="orig",
            except_name="Clever Impersonator",
        )
        apply_copy_effect(clone_instance, original, effect)

        assert clone_instance.card.name == "Clever Impersonator"
        assert clone_instance.card.power == 5

    def test_clone_with_additional_keywords(self):
        original = _make_creature("Bear", 2, 2, "1G")
        clone_card = _make_creature("Clone", 0, 0, "3U")
        clone_instance = CardInstance(card=clone_card, zone=Zone.BATTLEFIELD)

        effect = CopyEffect(
            source_id=clone_instance.instance_id,
            original_id="orig",
            additional_keywords={Keyword.HASTE},
        )
        apply_copy_effect(clone_instance, original, effect)

        assert clone_instance.card.name == "Bear"
        assert Keyword.HASTE in clone_instance.card.keywords


class TestCreateTokenCopy:
    def test_token_copy_basic(self):
        original = _make_creature("Soldier", 1, 1, "W")
        token = create_token_copy(original, owner_index=0)

        assert token.card.name == "Soldier"
        assert token.card.power == 1
        assert token.card.toughness == 1
        assert token.zone == Zone.BATTLEFIELD
        assert getattr(token, 'is_token', False) is True

    def test_token_copy_with_modifications(self):
        original = _make_creature("Cat", 1, 1, "W")
        token = create_token_copy(
            original,
            modifications={"power": 4, "toughness": 4},
        )

        assert token.card.name == "Cat"
        assert token.card.power == 4
        assert token.card.toughness == 4


class TestCopyEffectManager:
    def test_add_and_retrieve(self):
        mgr = CopyEffectManager()
        effect = CopyEffect(source_id="clone1", original_id="dragon1")
        mgr.add_copy_effect(effect)

        effects = mgr.get_effects_for("clone1")
        assert len(effects) == 1
        assert effects[0].original_id == "dragon1"

    def test_remove_effects(self):
        mgr = CopyEffectManager()
        effect = CopyEffect(source_id="clone1", original_id="dragon1")
        mgr.add_copy_effect(effect)
        mgr.remove_effects_from("clone1")

        effects = mgr.get_effects_for("clone1")
        assert len(effects) == 0

    def test_timestamps(self):
        mgr = CopyEffectManager()
        e1 = CopyEffect(source_id="c1", original_id="o1")
        e2 = CopyEffect(source_id="c2", original_id="o2")
        mgr.add_copy_effect(e1)
        mgr.add_copy_effect(e2)
        assert e1.timestamp < e2.timestamp
