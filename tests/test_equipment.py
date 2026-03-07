"""Tests for Equipment and Aura attachment system."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone, SuperType
from mtg_engine.core.equipment import (
    attach, can_enchant, can_equip, detach, get_equipment_bonuses,
)
from mtg_engine.core.game import Game
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost


def _make_creature(name="Bear", power=2, toughness=2, owner=0):
    card = Card(name=name, card_type=CardType.CREATURE, power=power, toughness=toughness)
    inst = CardInstance(card=card, zone=Zone.BATTLEFIELD, owner_index=owner, controller_index=owner)
    return inst


def _make_equipment(name="Sword", equip_cost="{1}", effects=None, owner=0):
    card = Card(
        name=name,
        card_type=CardType.ARTIFACT,
        subtypes=["Equipment"],
        effects=effects or [],
        keyword_params={Keyword.EQUIP: equip_cost},
    )
    inst = CardInstance(card=card, zone=Zone.BATTLEFIELD, owner_index=owner, controller_index=owner)
    return inst


def _make_aura(name="Rancor", enchant_type="creature", effects=None, owner=0):
    card = Card(
        name=name,
        card_type=CardType.ENCHANTMENT,
        subtypes=["Aura"],
        effects=effects or [{"type": "enchant", "target_type": enchant_type}],
    )
    inst = CardInstance(card=card, zone=Zone.BATTLEFIELD, owner_index=owner, controller_index=owner)
    return inst


class TestCanEquip:
    def test_valid_equip(self):
        equip = _make_equipment()
        creature = _make_creature()
        assert can_equip(equip, creature) is True

    def test_cant_equip_non_creature(self):
        equip = _make_equipment()
        land = CardInstance(
            card=Card(name="Forest", card_type=CardType.LAND),
            zone=Zone.BATTLEFIELD,
        )
        assert can_equip(equip, land) is False

    def test_cant_equip_self(self):
        equip = _make_equipment()
        assert can_equip(equip, equip) is False

    def test_cant_equip_different_controller(self):
        equip = _make_equipment(owner=0)
        creature = _make_creature(owner=1)
        assert can_equip(equip, creature) is False

    def test_cant_equip_from_hand(self):
        equip = _make_equipment()
        equip.zone = Zone.HAND
        creature = _make_creature()
        assert can_equip(equip, creature) is False

    def test_cant_equip_creature_in_graveyard(self):
        equip = _make_equipment()
        creature = _make_creature()
        creature.zone = Zone.GRAVEYARD
        assert can_equip(equip, creature) is False


class TestCanEnchant:
    def test_valid_enchant_creature(self):
        aura = _make_aura(enchant_type="creature")
        creature = _make_creature()
        assert can_enchant(aura, creature) is True

    def test_cant_enchant_non_creature_with_creature_aura(self):
        aura = _make_aura(enchant_type="creature")
        land = CardInstance(
            card=Card(name="Forest", card_type=CardType.LAND),
            zone=Zone.BATTLEFIELD,
        )
        assert can_enchant(aura, land) is False

    def test_can_enchant_hexproof_opponent(self):
        """can_enchant only checks type legality, not targeting restrictions.

        Hexproof prevents targeting (checked during casting), but an aura
        entering the battlefield without being cast can attach to anything
        with a legal type (CR 303.4f).
        """
        aura = _make_aura(enchant_type="creature", owner=0)
        creature = _make_creature(owner=1)
        creature.granted_keywords.add(Keyword.HEXPROOF)
        assert can_enchant(aura, creature) is True

    def test_can_enchant_own_hexproof(self):
        aura = _make_aura(enchant_type="creature", owner=0)
        creature = _make_creature(owner=0)
        creature.granted_keywords.add(Keyword.HEXPROOF)
        assert can_enchant(aura, creature) is True


class TestAttachDetach:
    def test_attach_equipment(self):
        equip = _make_equipment()
        creature = _make_creature()
        result = attach(equip, creature)
        assert result is True
        assert equip.attached_to == creature.instance_id
        assert equip.instance_id in creature.attachments

    def test_reattach_moves_equipment(self):
        equip = _make_equipment()
        bear1 = _make_creature(name="Bear1")
        bear2 = _make_creature(name="Bear2")

        attach(equip, bear1)
        assert equip.attached_to == bear1.instance_id

        attach(equip, bear2)
        assert equip.attached_to == bear2.instance_id
        assert equip.instance_id in bear2.attachments

    def test_detach(self):
        equip = _make_equipment()
        creature = _make_creature()
        attach(equip, creature)
        detach(equip, creature)
        assert equip.attached_to is None
        assert equip.instance_id not in creature.attachments


class TestEquipmentBonuses:
    def test_pump_bonus(self):
        equip = _make_equipment(
            effects=[{"type": "pump", "power": 2, "toughness": 0}],
        )
        creature = _make_creature()
        attach(equip, creature)

        lookup = {
            equip.instance_id: equip,
            creature.instance_id: creature,
        }
        bonuses = get_equipment_bonuses(creature, lookup)
        assert bonuses["power_mod"] == 2
        assert bonuses["toughness_mod"] == 0

    def test_keyword_bonus(self):
        equip = _make_equipment(
            effects=[{"type": "add_keyword", "keyword": "flying"}],
        )
        creature = _make_creature()
        attach(equip, creature)

        lookup = {
            equip.instance_id: equip,
            creature.instance_id: creature,
        }
        bonuses = get_equipment_bonuses(creature, lookup)
        assert Keyword.FLYING in bonuses["keywords"]


class TestGameEquip:
    def test_equip_in_game(self):
        sword = Card(
            name="Bonesplitter",
            card_type=CardType.ARTIFACT,
            cost=ManaCost(generic=1),
            subtypes=["Equipment"],
            effects=[{"type": "pump", "power": 2, "toughness": 0}],
            keyword_params={Keyword.EQUIP: "{1}"},
        )
        bear = Card(name="Bear", card_type=CardType.CREATURE, power=2, toughness=2)
        game = Game(["Alice", "Bob"], [[sword, bear], []])

        # Put both on battlefield
        sword_inst = game.state.cards[0]
        bear_inst = game.state.cards[1]
        sword_inst.zone = Zone.BATTLEFIELD
        bear_inst.zone = Zone.BATTLEFIELD

        # Give mana for equip cost
        game.state.players[0].mana_pool.add(
            __import__("mtg_engine.core.enums", fromlist=["Color"]).Color.COLORLESS, 1
        )

        # Set to main phase
        from mtg_engine.core.enums import Step
        game.state.step = Step.MAIN

        result = game.equip(0, sword_inst.instance_id, bear_inst.instance_id)
        assert result is True
        assert sword_inst.attached_to == bear_inst.instance_id
