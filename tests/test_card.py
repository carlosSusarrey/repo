"""Tests for card definitions and instances."""

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.mana import ManaCost


class TestCard:
    def test_creature_card(self):
        card = Card(
            name="Grizzly Bears",
            card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{G}"),
            power=2,
            toughness=2,
        )
        assert card.is_creature
        assert not card.is_land
        assert card.power == 2

    def test_instant_card(self):
        card = Card(
            name="Lightning Bolt",
            card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R}"),
        )
        assert card.is_instant
        assert not card.is_creature

    def test_land_card(self):
        card = Card(name="Mountain", card_type=CardType.LAND)
        assert card.is_land
        assert card.cost.converted_mana_cost == 0


class TestCardInstance:
    def test_instance_creation(self):
        card = Card(name="Forest", card_type=CardType.LAND)
        inst = CardInstance(card=card)
        assert inst.zone == Zone.LIBRARY
        assert not inst.tapped

    def test_tap_untap(self):
        card = Card(name="Forest", card_type=CardType.LAND)
        inst = CardInstance(card=card)
        inst.tap()
        assert inst.tapped
        inst.untap()
        assert not inst.tapped

    def test_damage_tracking(self):
        card = Card(
            name="Grizzly Bears",
            card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{G}"),
            power=2,
            toughness=2,
        )
        inst = CardInstance(card=card)
        assert not inst.lethal_damage
        inst.damage_marked = 2
        assert inst.lethal_damage

    def test_counters(self):
        card = Card(
            name="Grizzly Bears",
            card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{G}"),
            power=2,
            toughness=2,
        )
        inst = CardInstance(card=card)
        inst.counters["+1/+1"] = 2
        assert inst.current_power == 4
        assert inst.current_toughness == 4
