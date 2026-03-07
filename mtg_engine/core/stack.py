"""The stack - where spells and abilities wait to resolve."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Union, runtime_checkable


@runtime_checkable
class Stackable(Protocol):
    """Anything that can go on the stack: spells (cards) and abilities.

    CardInstance satisfies this protocol when on the stack.
    AbilityOnStack satisfies it for triggered/activated abilities.
    """

    @property
    def source_id(self) -> str: ...

    @property
    def controller_index(self) -> int: ...

    @property
    def card_name(self) -> str: ...

    @property
    def effects(self) -> list[dict[str, Any]]: ...

    @property
    def targets(self) -> list[str]: ...


@dataclass
class AbilityOnStack:
    """A triggered or activated ability on the stack (not a card)."""

    source_id: str
    controller_index: int
    card_name: str
    effects: list[dict[str, Any]] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        target_str = f" targeting {', '.join(self.targets)}" if self.targets else ""
        return f"{self.card_name}{target_str}"


# Backward-compat alias — tests that create StackItem get AbilityOnStack
StackItem = AbilityOnStack


class Stack:
    """The game stack - LIFO resolution of spells and abilities."""

    def __init__(self) -> None:
        self._items: list[Stackable] = []

    def push(self, item: Stackable) -> None:
        """Put an item on top of the stack."""
        self._items.append(item)

    def pop(self) -> Stackable | None:
        """Remove and return the top item from the stack."""
        if self._items:
            return self._items.pop()
        return None

    def peek(self) -> Stackable | None:
        """Look at the top item without removing it."""
        if self._items:
            return self._items[-1]
        return None

    def remove_by_source(self, source_id: str) -> Stackable | None:
        """Remove a stack item by its source ID (for countering spells)."""
        for i, item in enumerate(self._items):
            if item.source_id == source_id:
                return self._items.pop(i)
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
