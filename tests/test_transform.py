"""Tests for double-faced cards and transform."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost
from mtg_engine.core.transform import (
    DoubleFacedCard,
    setup_dfc,
    can_transform,
    transform,
    is_transformed,
    get_dfc,
    cast_as_back_face,
    get_front_face,
    get_back_face,
)


def _werewolf_dfc():
    front = Card(
        name="Villagers of Estwald",
        card_type=CardType.CREATURE,
        cost=ManaCost.parse("{2}{G}"),
        power=2,
        toughness=3,
        subtypes=["Human", "Werewolf"],
    )
    back = Card(
        name="Howlpack of Estwald",
        card_type=CardType.CREATURE,
        cost=ManaCost(),
        power=4,
        toughness=6,
        subtypes=["Werewolf"],
        keywords={Keyword.TRAMPLE},
    )
    return DoubleFacedCard(front_face=front, back_face=back)


def _pathway_mdfc():
    front = Card(
        name="Brightclimb Pathway",
        card_type=CardType.LAND,
        subtypes=["Plains"],
    )
    back = Card(
        name="Grimclimb Pathway",
        card_type=CardType.LAND,
        subtypes=["Swamp"],
    )
    return DoubleFacedCard(front_face=front, back_face=back, is_modal=True)


class TestSetupDFC:
    def test_setup_sets_front_face(self):
        dfc = _werewolf_dfc()
        instance = CardInstance(
            card=dfc.front_face,
            zone=Zone.BATTLEFIELD,
        )
        setup_dfc(instance, dfc)

        assert instance.card.name == "Villagers of Estwald"
        assert get_dfc(instance) is dfc
        assert not is_transformed(instance)

    def test_dfc_name(self):
        dfc = _werewolf_dfc()
        assert dfc.name == "Villagers of Estwald"


class TestTransform:
    def test_transform_to_back(self):
        dfc = _werewolf_dfc()
        instance = CardInstance(card=dfc.front_face, zone=Zone.BATTLEFIELD)
        setup_dfc(instance, dfc)

        assert can_transform(instance)
        result = transform(instance)
        assert result is True
        assert is_transformed(instance)
        assert instance.card.name == "Howlpack of Estwald"
        assert instance.card.power == 4
        assert instance.card.toughness == 6
        assert Keyword.TRAMPLE in instance.card.keywords

    def test_transform_back_to_front(self):
        dfc = _werewolf_dfc()
        instance = CardInstance(card=dfc.front_face, zone=Zone.BATTLEFIELD)
        setup_dfc(instance, dfc)

        transform(instance)
        assert instance.card.name == "Howlpack of Estwald"

        transform(instance)
        assert not is_transformed(instance)
        assert instance.card.name == "Villagers of Estwald"

    def test_non_dfc_cannot_transform(self):
        card = Card(name="Bear", card_type=CardType.CREATURE, power=2, toughness=2)
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        assert not can_transform(instance)
        assert not transform(instance)

    def test_mdfc_cannot_transform(self):
        dfc = _pathway_mdfc()
        instance = CardInstance(card=dfc.front_face, zone=Zone.BATTLEFIELD)
        setup_dfc(instance, dfc)

        assert not can_transform(instance)
        assert not transform(instance)


class TestMDFC:
    def test_cast_as_back_face(self):
        dfc = _pathway_mdfc()
        instance = CardInstance(card=dfc.front_face, zone=Zone.HAND)
        setup_dfc(instance, dfc)

        result = cast_as_back_face(instance)
        assert result is True
        assert instance.card.name == "Grimclimb Pathway"

    def test_cannot_cast_non_modal_as_back(self):
        dfc = _werewolf_dfc()
        instance = CardInstance(card=dfc.front_face, zone=Zone.HAND)
        setup_dfc(instance, dfc)

        result = cast_as_back_face(instance)
        assert result is False
        assert instance.card.name == "Villagers of Estwald"


class TestGetFaces:
    def test_get_front_and_back(self):
        dfc = _werewolf_dfc()
        instance = CardInstance(card=dfc.front_face, zone=Zone.BATTLEFIELD)
        setup_dfc(instance, dfc)

        front = get_front_face(instance)
        back = get_back_face(instance)
        assert front is not None
        assert front.name == "Villagers of Estwald"
        assert back is not None
        assert back.name == "Howlpack of Estwald"

    def test_non_dfc_returns_none(self):
        card = Card(name="Bear", card_type=CardType.CREATURE, power=2, toughness=2)
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        assert get_front_face(instance) is None
        assert get_back_face(instance) is None
