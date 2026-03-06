"""Tests for extended mana system: hybrid, Phyrexian, snow, X costs."""

import pytest

from mtg_engine.core.enums import Color
from mtg_engine.core.mana import HybridMana, ManaCost, ManaPool, PhyrexianMana


class TestHybridManaParsing:
    def test_parse_hybrid(self):
        cost = ManaCost.parse("{W/U}")
        assert len(cost.hybrid) == 1
        assert cost.hybrid[0].color1 == "W"
        assert cost.hybrid[0].color2 == "U"

    def test_parse_multiple_hybrid(self):
        cost = ManaCost.parse("{W/U}{W/U}{R}")
        assert len(cost.hybrid) == 2
        assert cost.red == 1

    def test_hybrid_colors(self):
        cost = ManaCost.parse("{W/U}")
        assert Color.WHITE in cost.colors
        assert Color.BLUE in cost.colors

    def test_hybrid_cmc(self):
        cost = ManaCost.parse("{2}{W/U}{W/U}")
        assert cost.converted_mana_cost == 4

    def test_hybrid_str(self):
        cost = ManaCost.parse("{W/U}")
        assert "{W/U}" in str(cost)


class TestPhyrexianManaParsing:
    def test_parse_phyrexian(self):
        cost = ManaCost.parse("{R/P}")
        assert len(cost.phyrexian) == 1
        assert cost.phyrexian[0].color == "R"

    def test_phyrexian_colors(self):
        cost = ManaCost.parse("{R/P}")
        assert Color.RED in cost.colors

    def test_phyrexian_cmc(self):
        cost = ManaCost.parse("{1}{R/P}{R/P}")
        assert cost.converted_mana_cost == 3

    def test_phyrexian_str(self):
        cost = ManaCost.parse("{W/P}")
        assert "{W/P}" in str(cost)


class TestSnowMana:
    def test_parse_snow(self):
        cost = ManaCost.parse("{S}{S}")
        assert cost.snow == 2

    def test_snow_cmc(self):
        cost = ManaCost.parse("{2}{S}")
        assert cost.converted_mana_cost == 3

    def test_snow_str(self):
        cost = ManaCost.parse("{S}")
        assert "{S}" in str(cost)


class TestXCosts:
    def test_parse_x(self):
        cost = ManaCost.parse("{X}{R}")
        assert cost.x_count == 1
        assert cost.red == 1
        assert cost.has_x

    def test_double_x(self):
        cost = ManaCost.parse("{X}{X}{G}")
        assert cost.x_count == 2
        assert cost.green == 1

    def test_x_cmc_without_value(self):
        cost = ManaCost.parse("{X}{R}")
        # X is 0 when not on stack
        assert cost.converted_mana_cost == 1

    def test_x_mana_value_with_x(self):
        cost = ManaCost.parse("{X}{R}")
        assert cost.mana_value_with_x(5) == 6

    def test_double_x_mana_value(self):
        cost = ManaCost.parse("{X}{X}{R}")
        assert cost.mana_value_with_x(3) == 7  # 3+3+1

    def test_x_str(self):
        cost = ManaCost.parse("{X}{R}")
        assert str(cost).startswith("{X}")

    def test_compact_x(self):
        cost = ManaCost.parse("XR")
        assert cost.x_count == 1
        assert cost.red == 1


class TestColorlessMana:
    def test_parse_colorless(self):
        cost = ManaCost.parse("{C}{C}")
        assert cost.colorless == 2

    def test_colorless_cmc(self):
        cost = ManaCost.parse("{2}{C}")
        assert cost.converted_mana_cost == 3

    def test_colorless_str(self):
        cost = ManaCost.parse("{C}")
        assert "{C}" in str(cost)


class TestManaPoolHybrid:
    def test_can_pay_hybrid_with_first_color(self):
        pool = ManaPool(white=1)
        cost = ManaCost.parse("{W/U}")
        assert pool.can_pay(cost)

    def test_can_pay_hybrid_with_second_color(self):
        pool = ManaPool(blue=1)
        cost = ManaCost.parse("{W/U}")
        assert pool.can_pay(cost)

    def test_cannot_pay_hybrid_wrong_color(self):
        pool = ManaPool(red=1)
        cost = ManaCost.parse("{W/U}")
        assert not pool.can_pay(cost)

    def test_pay_hybrid(self):
        pool = ManaPool(white=2)
        cost = ManaCost.parse("{W/U}")
        assert pool.pay(cost)
        assert pool.white == 1


class TestManaPoolColorless:
    def test_colorless_specific(self):
        pool = ManaPool(colorless=2)
        cost = ManaCost.parse("{C}{C}")
        assert pool.can_pay(cost)
        pool.pay(cost)
        assert pool.colorless == 0

    def test_colored_cannot_pay_colorless(self):
        pool = ManaPool(red=2)
        cost = ManaCost.parse("{C}")
        assert not pool.can_pay(cost)


class TestManaPoolSnow:
    def test_snow_pool(self):
        pool = ManaPool()
        pool.add(Color.GREEN, 1, is_snow=True)
        assert pool.green == 1
        assert pool.snow == 1


class TestBackwardsCompatibility:
    """Ensure existing mana functionality still works."""

    def test_basic_cost(self):
        cost = ManaCost.parse("{2}{R}{R}")
        assert cost.generic == 2
        assert cost.red == 2
        assert cost.converted_mana_cost == 4

    def test_basic_pool(self):
        pool = ManaPool(red=3)
        cost = ManaCost.parse("{1}{R}{R}")
        assert pool.can_pay(cost)
        pool.pay(cost)
        assert pool.red == 0

    def test_no_cost(self):
        cost = ManaCost()
        assert cost.converted_mana_cost == 0
        assert str(cost) == "{0}"
        assert not cost.has_x
