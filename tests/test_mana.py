"""Tests for mana cost parsing and mana pool management."""

from mtg_engine.core.mana import ManaCost, ManaPool
from mtg_engine.core.enums import Color


class TestManaCost:
    def test_parse_simple_colored(self):
        cost = ManaCost.parse("{R}")
        assert cost.red == 1
        assert cost.converted_mana_cost == 1

    def test_parse_generic_and_colored(self):
        cost = ManaCost.parse("{2}{R}{R}")
        assert cost.generic == 2
        assert cost.red == 2
        assert cost.converted_mana_cost == 4

    def test_parse_multicolor(self):
        cost = ManaCost.parse("{W}{U}{B}{R}{G}")
        assert cost.white == 1
        assert cost.blue == 1
        assert cost.black == 1
        assert cost.red == 1
        assert cost.green == 1
        assert cost.converted_mana_cost == 5

    def test_colors_property(self):
        cost = ManaCost.parse("{1}{R}{G}")
        assert cost.colors == {Color.RED, Color.GREEN}

    def test_zero_cost(self):
        cost = ManaCost()
        assert cost.converted_mana_cost == 0
        assert str(cost) == "{0}"

    def test_str_representation(self):
        cost = ManaCost.parse("{2}{R}")
        assert str(cost) == "{2}{R}"


class TestManaPool:
    def test_add_mana(self):
        pool = ManaPool()
        pool.add(Color.RED, 2)
        assert pool.red == 2
        assert pool.total == 2

    def test_can_pay_exact(self):
        pool = ManaPool(red=1)
        cost = ManaCost.parse("{R}")
        assert pool.can_pay(cost)

    def test_cannot_pay_insufficient(self):
        pool = ManaPool(red=1)
        cost = ManaCost.parse("{R}{R}")
        assert not pool.can_pay(cost)

    def test_pay_generic_with_colored(self):
        pool = ManaPool(red=3)
        cost = ManaCost.parse("{2}{R}")
        assert pool.can_pay(cost)
        assert pool.pay(cost)
        assert pool.red == 0

    def test_pay_returns_false_if_cannot(self):
        pool = ManaPool(red=1)
        cost = ManaCost.parse("{2}{R}")
        assert not pool.pay(cost)
        # Pool should be unchanged
        assert pool.red == 1

    def test_empty_pool(self):
        pool = ManaPool(white=3, blue=2, red=1)
        pool.empty()
        assert pool.total == 0
