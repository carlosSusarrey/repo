"""Mana costs and mana pool management.

Supports standard mana, hybrid mana ({W/U}), Phyrexian mana ({W/P}),
snow mana ({S}), colorless-specific mana ({C}), and X costs ({X}).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from mtg_engine.core.enums import Color


@dataclass(frozen=True)
class HybridMana:
    """A hybrid mana symbol that can be paid with either color.

    E.g., {W/U} can be paid with white or blue.
    """
    color1: str  # e.g., "W"
    color2: str  # e.g., "U"

    def __str__(self) -> str:
        return f"{{{self.color1}/{self.color2}}}"


@dataclass(frozen=True)
class PhyrexianMana:
    """A Phyrexian mana symbol — pay with mana or 2 life.

    E.g., {W/P} can be paid with W or 2 life.
    """
    color: str  # e.g., "W"

    def __str__(self) -> str:
        return f"{{{self.color}/P}}"


@dataclass(frozen=True)
class ManaCost:
    """Represents a mana cost like {2}{R}{R}.

    Extended to support hybrid, Phyrexian, snow, colorless, and X costs.
    """

    generic: int = 0
    white: int = 0
    blue: int = 0
    black: int = 0
    red: int = 0
    green: int = 0
    colorless: int = 0     # {C} — specifically colorless (not generic)
    snow: int = 0           # {S} — paid with mana from a snow source
    x_count: int = 0        # Number of X in the cost
    hybrid: tuple[HybridMana, ...] = ()
    phyrexian: tuple[PhyrexianMana, ...] = ()

    @classmethod
    def parse(cls, cost_str: str) -> ManaCost:
        """Parse a mana cost string like '{2}{R}{R}' or '2RR'.

        Supports:
        - {X} — X cost
        - {W/U} — hybrid mana
        - {W/P} — Phyrexian mana
        - {S} — snow mana
        - {C} — colorless mana (specifically colorless)
        """
        generic = 0
        colors = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}
        colorless = 0
        snow = 0
        x_count = 0
        hybrid: list[HybridMana] = []
        phyrexian: list[PhyrexianMana] = []

        # Handle {X} notation
        tokens = re.findall(r"\{([^}]+)\}", cost_str)
        if tokens:
            for token in tokens:
                if token == "X":
                    x_count += 1
                elif token == "S":
                    snow += 1
                elif token == "C":
                    colorless += 1
                elif "/" in token:
                    parts = token.split("/")
                    if len(parts) == 2:
                        if parts[1] == "P":
                            phyrexian.append(PhyrexianMana(color=parts[0]))
                        else:
                            hybrid.append(HybridMana(color1=parts[0], color2=parts[1]))
                elif token.isdigit():
                    generic += int(token)
                elif token in colors:
                    colors[token] += 1
        else:
            # Handle compact notation like "2RR"
            i = 0
            while i < len(cost_str):
                if cost_str[i] == "X":
                    x_count += 1
                    i += 1
                elif cost_str[i] == "S":
                    snow += 1
                    i += 1
                elif cost_str[i] == "C":
                    colorless += 1
                    i += 1
                elif cost_str[i].isdigit():
                    num = ""
                    while i < len(cost_str) and cost_str[i].isdigit():
                        num += cost_str[i]
                        i += 1
                    generic += int(num)
                elif cost_str[i] in colors:
                    colors[cost_str[i]] += 1
                    i += 1
                else:
                    i += 1

        return cls(
            generic=generic,
            white=colors["W"],
            blue=colors["U"],
            black=colors["B"],
            red=colors["R"],
            green=colors["G"],
            colorless=colorless,
            snow=snow,
            x_count=x_count,
            hybrid=tuple(hybrid),
            phyrexian=tuple(phyrexian),
        )

    @property
    def converted_mana_cost(self) -> int:
        """Total mana value (converted mana cost).

        X is 0 when not on the stack. Hybrid counts as 1 each.
        Phyrexian counts as 1 each.
        """
        return (
            self.generic + self.white + self.blue + self.black
            + self.red + self.green + self.colorless + self.snow
            + len(self.hybrid) + len(self.phyrexian)
        )

    def mana_value_with_x(self, x_value: int = 0) -> int:
        """Mana value with a specific X value (on the stack)."""
        return self.converted_mana_cost + (self.x_count * x_value)

    @property
    def has_x(self) -> bool:
        return self.x_count > 0

    @property
    def colors(self) -> set[Color]:
        """Set of colors in this mana cost."""
        result = set()
        if self.white > 0:
            result.add(Color.WHITE)
        if self.blue > 0:
            result.add(Color.BLUE)
        if self.black > 0:
            result.add(Color.BLACK)
        if self.red > 0:
            result.add(Color.RED)
        if self.green > 0:
            result.add(Color.GREEN)
        # Hybrid mana contributes both colors
        color_map = {"W": Color.WHITE, "U": Color.BLUE, "B": Color.BLACK,
                     "R": Color.RED, "G": Color.GREEN}
        for h in self.hybrid:
            if h.color1 in color_map:
                result.add(color_map[h.color1])
            if h.color2 in color_map:
                result.add(color_map[h.color2])
        # Phyrexian mana contributes its color
        for p in self.phyrexian:
            if p.color in color_map:
                result.add(color_map[p.color])
        return result

    def __add__(self, other: ManaCost) -> ManaCost:
        """Combine two mana costs (e.g. spell cost + ward cost)."""
        return ManaCost(
            generic=self.generic + other.generic,
            white=self.white + other.white,
            blue=self.blue + other.blue,
            black=self.black + other.black,
            red=self.red + other.red,
            green=self.green + other.green,
            colorless=self.colorless + other.colorless,
            snow=self.snow + other.snow,
            x_count=self.x_count + other.x_count,
            hybrid=self.hybrid + other.hybrid,
            phyrexian=self.phyrexian + other.phyrexian,
        )

    def __str__(self) -> str:
        parts = []
        parts.extend(["{X}"] * self.x_count)
        if self.generic > 0:
            parts.append(f"{{{self.generic}}}")
        parts.extend(["{W}"] * self.white)
        parts.extend(["{U}"] * self.blue)
        parts.extend(["{B}"] * self.black)
        parts.extend(["{R}"] * self.red)
        parts.extend(["{G}"] * self.green)
        parts.extend(["{C}"] * self.colorless)
        parts.extend(["{S}"] * self.snow)
        parts.extend([str(h) for h in self.hybrid])
        parts.extend([str(p) for p in self.phyrexian])
        return "".join(parts) if parts else "{0}"


@dataclass
class ManaPool:
    """A player's available mana."""

    white: int = 0
    blue: int = 0
    black: int = 0
    red: int = 0
    green: int = 0
    colorless: int = 0
    snow: int = 0  # Snow mana available (from snow sources)

    def add(self, color: Color, amount: int = 1, is_snow: bool = False) -> None:
        match color:
            case Color.WHITE:
                self.white += amount
            case Color.BLUE:
                self.blue += amount
            case Color.BLACK:
                self.black += amount
            case Color.RED:
                self.red += amount
            case Color.GREEN:
                self.green += amount
            case Color.COLORLESS:
                self.colorless += amount
        if is_snow:
            self.snow += amount

    def can_pay(self, cost: ManaCost) -> bool:
        """Check if this pool can pay the given mana cost."""
        available = {
            "W": self.white,
            "U": self.blue,
            "B": self.black,
            "R": self.red,
            "G": self.green,
        }
        remaining = available.copy()

        # Pay colored costs first
        for color_key, needed in [
            ("W", cost.white), ("U", cost.blue), ("B", cost.black),
            ("R", cost.red), ("G", cost.green),
        ]:
            if remaining[color_key] < needed:
                return False
            remaining[color_key] -= needed

        # Pay colorless-specific ({C}) from colorless pool
        remaining_colorless = self.colorless
        if remaining_colorless < cost.colorless:
            return False
        remaining_colorless -= cost.colorless

        # Pay snow mana from snow sources
        if self.snow < cost.snow:
            return False

        # Hybrid: each can be paid by either color
        for h in cost.hybrid:
            if remaining.get(h.color1, 0) > 0:
                remaining[h.color1] -= 1
            elif remaining.get(h.color2, 0) > 0:
                remaining[h.color2] -= 1
            else:
                return False

        # Phyrexian: can be paid by color or 2 life (life payment handled at game level)
        # For can_pay, we check if the color is available
        for p in cost.phyrexian:
            if remaining.get(p.color, 0) > 0:
                remaining[p.color] -= 1
            # else: would pay 2 life — always "payable" at pool level

        # Check if remaining mana + colorless covers generic cost
        total_remaining = sum(remaining.values()) + remaining_colorless
        return total_remaining >= cost.generic

    def pay(self, cost: ManaCost) -> bool:
        """Pay a mana cost from this pool. Returns False if unable."""
        if not self.can_pay(cost):
            return False

        self.white -= cost.white
        self.blue -= cost.blue
        self.black -= cost.black
        self.red -= cost.red
        self.green -= cost.green

        # Pay colorless-specific
        self.colorless -= cost.colorless

        # Pay hybrid
        for h in cost.hybrid:
            color_attr_map = {"W": "white", "U": "blue", "B": "black",
                              "R": "red", "G": "green"}
            attr1 = color_attr_map.get(h.color1)
            attr2 = color_attr_map.get(h.color2)
            if attr1 and getattr(self, attr1) > 0:
                setattr(self, attr1, getattr(self, attr1) - 1)
            elif attr2 and getattr(self, attr2) > 0:
                setattr(self, attr2, getattr(self, attr2) - 1)

        # Pay Phyrexian (color payment; life payment handled at game level)
        for p in cost.phyrexian:
            color_attr_map = {"W": "white", "U": "blue", "B": "black",
                              "R": "red", "G": "green"}
            attr = color_attr_map.get(p.color)
            if attr and getattr(self, attr) > 0:
                setattr(self, attr, getattr(self, attr) - 1)

        # Pay generic from colorless first, then from colored
        generic_remaining = cost.generic
        pay_from_colorless = min(self.colorless, generic_remaining)
        self.colorless -= pay_from_colorless
        generic_remaining -= pay_from_colorless

        # Pay remaining generic from colored mana (largest pool first)
        for attr in sorted(["white", "blue", "black", "red", "green"],
                           key=lambda a: getattr(self, a), reverse=True):
            if generic_remaining <= 0:
                break
            available = getattr(self, attr)
            pay = min(available, generic_remaining)
            setattr(self, attr, available - pay)
            generic_remaining -= pay

        return True

    def empty(self) -> None:
        """Empty the mana pool (happens at end of each step)."""
        self.white = self.blue = self.black = self.red = self.green = self.colorless = 0
        self.snow = 0

    @property
    def total(self) -> int:
        return self.white + self.blue + self.black + self.red + self.green + self.colorless
