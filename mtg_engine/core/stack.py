"""The stack - where spells and abilities wait to resolve."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StackItem:
    """An item on the stack (spell or ability)."""

    source_id: str
    controller_index: int
    card_name: str
    effects: list[dict[str, Any]] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        target_str = f" targeting {', '.join(self.targets)}" if self.targets else ""
        return f"{self.card_name}{target_str}"


class Stack:
    """The game stack - LIFO resolution of spells and abilities."""

    def __init__(self) -> None:
        self._items: list[StackItem] = []

    def push(self, item: StackItem) -> None:
        """Put an item on top of the stack."""
        self._items.append(item)

    def pop(self) -> StackItem | None:
        """Remove and return the top item from the stack."""
        if self._items:
            return self._items.pop()
        return None

    def peek(self) -> StackItem | None:
        """Look at the top item without removing it."""
        if self._items:
            return self._items[-1]
        return None

    @property
    def is_empty(self) -> bool:
        return len(self._items) == 0

    @property
    def size(self) -> int:
        return len(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(reversed(self._items))

    def __str__(self) -> str:
        if self.is_empty:
            return "Stack: (empty)"
        items_str = "\n  ".join(str(item) for item in self)
        return f"Stack ({self.size}):\n  {items_str}"
