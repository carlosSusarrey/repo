"""Tests for face-down cards (morph, disguise, manifest)."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.face_down import (
    FACE_DOWN_CARD,
    cast_face_down,
    can_turn_face_up,
    turn_face_up,
    is_face_down,
    get_morph_cost,
    manifest,
)
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost


def _make_morph_creature():
    return Card(
        name="Willbender",
        card_type=CardType.CREATURE,
        cost=ManaCost.parse("{1}{U}"),
        power=1,
        toughness=2,
        keywords={Keyword.FLYING},
    )


class TestCastFaceDown:
    def test_cast_face_down_morph(self):
        card = _make_morph_creature()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)

        morph_cost = ManaCost.parse("{1}{U}")
        cast_face_down(instance, morph_cost=morph_cost)

        assert is_face_down(instance)
        assert instance.card.name == ""
        assert instance.card.power == 2
        assert instance.card.toughness == 2
        assert instance.card.card_type == CardType.CREATURE
        # Should have no keywords from original
        assert Keyword.FLYING not in instance.card.keywords

    def test_cast_face_down_disguise_grants_ward(self):
        card = _make_morph_creature()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)

        disguise_cost = ManaCost.parse("{1}{U}")
        cast_face_down(instance, disguise_cost=disguise_cost)

        assert is_face_down(instance)
        assert Keyword.WARD in instance.keywords

    def test_not_face_down_initially(self):
        card = _make_morph_creature()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        assert not is_face_down(instance)


class TestTurnFaceUp:
    def test_turn_face_up_restores_card(self):
        card = _make_morph_creature()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)

        morph_cost = ManaCost.parse("{1}{U}")
        cast_face_down(instance, morph_cost=morph_cost)
        assert is_face_down(instance)

        turn_face_up(instance)
        assert not is_face_down(instance)
        assert instance.card.name == "Willbender"
        assert instance.card.power == 1
        assert instance.card.toughness == 2
        assert Keyword.FLYING in instance.card.keywords

    def test_disguise_ward_removed_on_turn_up(self):
        card = _make_morph_creature()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)

        disguise_cost = ManaCost.parse("{1}{U}")
        cast_face_down(instance, disguise_cost=disguise_cost)
        assert Keyword.WARD in instance.keywords

        turn_face_up(instance)
        assert Keyword.WARD not in instance.keywords

    def test_can_turn_face_up(self):
        card = _make_morph_creature()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)

        # Not face down, can't turn up
        assert not can_turn_face_up(instance)

        morph_cost = ManaCost.parse("{1}{U}")
        cast_face_down(instance, morph_cost=morph_cost)
        assert can_turn_face_up(instance)

    def test_cannot_turn_up_without_cost(self):
        card = _make_morph_creature()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)

        # Face down without morph/disguise cost
        from mtg_engine.core.face_down import FaceDownState
        state = FaceDownState(is_face_down=True, original_card=card)
        instance._face_down_state = state
        instance.card = FACE_DOWN_CARD

        assert not can_turn_face_up(instance)


class TestGetMorphCost:
    def test_morph_cost(self):
        card = _make_morph_creature()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)

        morph_cost = ManaCost.parse("{2}{U}")
        cast_face_down(instance, morph_cost=morph_cost)

        cost = get_morph_cost(instance)
        assert cost is not None
        assert cost.blue == 1
        assert cost.generic == 2

    def test_disguise_cost_preferred(self):
        card = _make_morph_creature()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)

        morph_cost = ManaCost.parse("{2}{U}")
        disguise_cost = ManaCost.parse("{1}{U}")
        cast_face_down(instance, morph_cost=morph_cost, disguise_cost=disguise_cost)

        cost = get_morph_cost(instance)
        assert cost is not None
        assert cost.generic == 1  # Disguise cost preferred

    def test_no_cost_if_not_face_down(self):
        card = _make_morph_creature()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)
        assert get_morph_cost(instance) is None


class TestManifest:
    def test_manifest_creature(self):
        card = _make_morph_creature()
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)

        manifest(instance)
        assert is_face_down(instance)
        assert instance.card.power == 2
        assert instance.card.toughness == 2

        # Can turn face-up by paying mana cost
        assert can_turn_face_up(instance)

    def test_manifest_noncreature(self):
        card = Card(
            name="Lightning Bolt",
            card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R}"),
        )
        instance = CardInstance(card=card, zone=Zone.BATTLEFIELD)

        manifest(instance)
        assert is_face_down(instance)
        # Non-creature can't be turned face-up via manifest
        assert not can_turn_face_up(instance)
