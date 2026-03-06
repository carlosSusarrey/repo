"""Mana costs and mana pool management."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from mtg_engine.core.enums import Color


@dataclass(frozen=True)
class ManaCost:
    """Represents a mana cost like {2}{R}{R}."""

    generic: int = 0
    white: int = 0
    blue: int = 0
    black: int = 0
    red: int = 0
    green: int = 0

    @classmethod
    def parse(cls, cost_str: str) -> ManaCost:
        """Parse a mana cost string like '{2}{R}{R}' or '2RR'."""
        generic = 0
        colors = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}

        # Handle {X} notation
        tokens = re.findall(r"\{([^}]+)\}", cost_str)
        if tokens:
            for token in tokens:
                if token.isdigit():
                    generic += int(token)
                elif token in colors:
                    colors[token] += 1
        else:
            # Handle compact notation like "2RR"
            i = 0
            while i < len(cost_str):
                if cost_str[i].isdigit():
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
        )

    @property
    def converted_mana_cost(self) -> int:
        """Total mana value (converted mana cost)."""
        return self.generic + self.white + self.blue + self.black + self.red + self.green

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
        return result

    def __str__(self) -> str:
        parts = []
        if self.generic > 0:
            parts.append(f"{{{self.generic}}}")
        parts.extend(["{W}"] * self.white)
        parts.extend(["{U}"] * self.blue)
        parts.extend(["{B}"] * self.black)
        parts.extend(["{R}"] * self.red)
        parts.extend(["{G}"] * self.green)
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

    def add(self, color: Color, amount: int = 1) -> None:
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

        # Check if remaining mana + colorless covers generic cost
        total_remaining = sum(remaining.values()) + self.colorless
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

    @property
    def total(self) -> int:
        return self.white + self.blue + self.black + self.red + self.green + self.colorless
