# Plan: Centralize Ability Events

## Problem

Triggers and replacement effects react to the same underlying game events, but use two separate enum registries (`TriggerEvent` with 22 members, `ReplacementType` with 8 members) with different names for overlapping concepts. Event data is passed as untyped dicts with ad-hoc keys at each of ~15 call sites. Adding a new mechanic (e.g. Prowess, Cycling) requires:

1. Updating the right enum (or both)
2. Finding the correct emit site in `game.py` / `game_state.py`
3. Hand-building an event dict (hoping keys match what consumers expect)

## Solution: Unified GameEvent + EventBus

### Step 1: Create `mtg_engine/core/events.py` — Unified event types

**A unified `GameEvent` enum** that replaces both `TriggerEvent` and `ReplacementType`:

```python
class GameEvent(Enum):
    # Zone changes
    ENTERS_BATTLEFIELD = auto()
    LEAVES_BATTLEFIELD = auto()
    DIES = auto()
    ENTERS_GRAVEYARD = auto()
    IS_EXILED = auto()
    ENTERS_HAND = auto()
    PUT_ON_TOP_LIBRARY = auto()
    PUT_ON_BOTTOM_LIBRARY = auto()
    ZONE_CHANGE = auto()  # generic (for ReplacementType.ZONE_CHANGE)

    # Spells
    CAST = auto()

    # Combat
    ATTACKS = auto()
    BLOCKS = auto()
    BECOMES_BLOCKED = auto()
    DEALS_COMBAT_DAMAGE = auto()
    DEALS_COMBAT_DAMAGE_TO_PLAYER = auto()

    # Phase/step
    BEGIN_UPKEEP = auto()
    BEGIN_COMBAT = auto()
    END_STEP = auto()

    # Resources
    GAIN_LIFE = auto()
    LOSE_LIFE = auto()
    DRAW_CARD = auto()
    LAND_ENTERS = auto()
    DAMAGE = auto()
    DISCARD = auto()
    COUNTER_PLACED = auto()
```

**Typed event data classes** (one per event category) so producers and consumers agree on shape:

```python
@dataclass
class ZoneChangeEventData:
    card_id: str
    card: Any  # CardInstance
    player_index: int
    from_zone: Zone | None = None
    to_zone: Zone | None = None
    cause: str = ""

@dataclass
class DamageEventData:
    source_id: str
    target_id: str
    amount: int
    is_combat: bool = False

@dataclass
class LifeEventData:
    player_index: int
    amount: int

@dataclass
class SpellEventData:
    card_id: str
    card: Any
    player_index: int

@dataclass
class CombatEventData:
    card_id: str
    card: Any
    player_index: int
    amount: int = 0  # for damage events

@dataclass
class CounterEventData:
    card_id: str
    card: Any
    counter_type: str
    amount: int
    player_index: int

@dataclass
class DrawEventData:
    player_index: int

@dataclass
class PhaseEventData:
    player_index: int
```

Each data class will also have a `.to_dict()` method returning the dict form for backward compatibility with existing trigger matching / replacement effect logic. This avoids a big-bang rewrite of consumers.

### Step 2: Create `EventBus` in `events.py`

```python
class EventBus:
    """Central event dispatcher. Routes events to triggers and replacements."""

    def __init__(self, trigger_manager, replacement_manager):
        self._triggers = trigger_manager
        self._replacements = replacement_manager

    def emit(self, event: GameEvent, data: EventDataBase,
             battlefield_cards: list, extra_cards: list | None = None
    ) -> EventDataBase | None:
        """Emit a game event.

        1. Check replacement effects (for replaceable events)
        2. If not prevented, check triggered abilities

        Returns modified event data, or None if event was prevented.
        """
        # Replacement effects (only for replaceable event types)
        if event in _REPLACEABLE_EVENTS:
            result = self._replacements.check_replacement(
                _EVENT_TO_REPLACEMENT[event], data.to_dict()
            )
            if result is None:
                return None
            data = data.from_dict(result)

        # Trigger check
        self._triggers.check_triggers(event, data.to_dict(),
                                       battlefield_cards, extra_cards)
        return data
```

The mapping `_EVENT_TO_REPLACEMENT` maps `GameEvent` → `ReplacementType` for the subset of events that are replaceable. This lets `ReplacementEffectManager` continue working unchanged internally — we just change how it's called.

Similarly, `_EVENT_TO_TRIGGER` maps `GameEvent` → `TriggerEvent` for backward compat with `TriggerManager` internals.

### Step 3: Add `EventBus` to `GameState`

In `game_state.py`, add:
```python
self.event_bus = EventBus(self.triggers, self.replacement_effects)
```

### Step 4: Refactor emit sites to use `event_bus.emit()`

Replace all ~15 hand-built emit sites with `self.state.event_bus.emit()` calls. **Each site becomes a 2-3 line call instead of 5-10 lines of dict building + separate trigger/replacement checks.**

Specific sites to refactor (grouped by file):

**`game_state.py` — `move_card()`:**
- ETB replacement check (lines 127-134) → `event_bus.emit(GameEvent.ENTERS_BATTLEFIELD, ...)`
- LEAVES_BATTLEFIELD trigger (lines 208-214) → `event_bus.emit(GameEvent.LEAVES_BATTLEFIELD, ...)`
- ENTERS_GRAVEYARD trigger (lines 222-228) → `event_bus.emit(GameEvent.ENTERS_GRAVEYARD, ...)`
- IS_EXILED trigger (lines 229-235) → `event_bus.emit(GameEvent.IS_EXILED, ...)`
- ENTERS_HAND trigger (lines 236-242) → `event_bus.emit(GameEvent.ENTERS_HAND, ...)`
- PUT_ON_TOP/BOTTOM_LIBRARY trigger (lines 243-254) → `event_bus.emit(GameEvent.PUT_ON_TOP_LIBRARY, ...)`

**`game_state.py` — `check_state_based_actions()`:**
- DIE replacement + DIES trigger for SBA deaths (lines 407-418) → `event_bus.emit(GameEvent.DIES, ...)`

**`game.py` — `draw_card()`:**
- DRAW replacement (lines 91-97) → `event_bus.emit(GameEvent.DRAW_CARD, ...)`

**`game.py` — `play_land()`:**
- LAND_ENTERS + ETB triggers (lines 137-145) → `event_bus.emit(GameEvent.LAND_ENTERS, ...)` + `event_bus.emit(GameEvent.ENTERS_BATTLEFIELD, ...)`

**`game.py` — `cast_spell()`:**
- CAST trigger (lines 276-282) → `event_bus.emit(GameEvent.CAST, ...)`

**`game.py` — `_resolve_effect()` damage:**
- DAMAGE replacement (lines 419-422) → `event_bus.emit(GameEvent.DAMAGE, ...)`

**`game.py` — `_resolve_effect()` destroy:**
- DIE replacement + DIES trigger (lines 478-499) → `event_bus.emit(GameEvent.DIES, ...)`

**`game.py` — `_resolve_effect()` gain_life:**
- LIFE_GAIN replacement (lines 511-513) → `event_bus.emit(GameEvent.GAIN_LIFE, ...)`

**`game.py` — `_resolve_effect()` sacrifice (x2):**
- DIE replacement + DIES trigger for self-sac (lines 660-680) → `event_bus.emit(GameEvent.DIES, ...)`
- DIE replacement + DIES trigger for target-sac (lines 688-709) → `event_bus.emit(GameEvent.DIES, ...)`

**`game.py` — `declare_attackers()`:**
- ATTACKS trigger (lines 809-814) → `event_bus.emit(GameEvent.ATTACKS, ...)`

**`game.py` — `_apply_damage()` combat:**
- DEALS_COMBAT_DAMAGE_TO_PLAYER trigger (lines 884-889) → `event_bus.emit(GameEvent.DEALS_COMBAT_DAMAGE_TO_PLAYER, ...)`

### Step 5: Unify DSL grammar event names

The grammar currently has **two separate terminals** with inconsistent naming:

```
// Current — two terminals, inconsistent names
TRIGGER_EVENT: "enters_battlefield" | "dies" | "cast" | ...
REPLACEMENT_TYPE: "enter_battlefield" | "die" | "damage" | ...
```

**Problem**: `"enters_battlefield"` (trigger) vs `"enter_battlefield"` (replacement), `"dies"` vs `"die"`, `"draw"` vs `"draw_card"`. Card authors must remember which spelling goes where.

**Solution**: Create a single `GAME_EVENT` terminal that both `when()` and `replace()` reference. Use the trigger-style names (verb conjugated for "when X happens") since those are more natural and there are more of them:

```
// grammar.py — unified terminal
GAME_EVENT: "enters_battlefield" | "leaves_battlefield" | "dies"
          | "enters_graveyard" | "is_exiled" | "enters_hand"
          | "put_on_top" | "put_on_bottom"
          | "attacks" | "blocks" | "deals_combat_damage_to_player"
          | "begin_upkeep" | "end_step" | "land_enters" | "cast"
          | "transforms" | "level_up"
          | "damage" | "draw_card" | "gain_life" | "lose_life"
          | "discard" | "counter_placed" | "zone_change"

// Updated rules
triggered_prop: "when(" GAME_EVENT "," source_filter_list "):" effect
             | "when(" GAME_EVENT "):" effect
replacement_prop: "replace(" GAME_EVENT "):" replacement_action
               | "replace(" GAME_EVENT "," REPLACEMENT_SCOPE "):" replacement_action
```

**Backward compat for replacement names**: The parser's `replacement_prop` handler will map old-style names to new ones:

```python
_REPLACEMENT_NAME_ALIASES = {
    "enter_battlefield": "enters_battlefield",
    "die": "dies",
    "draw": "draw_card",
    "life_gain": "gain_life",
}
```

This mapping is applied in the parser, so existing `.mtg` card files using `replace(die):` still work. New cards should use `replace(dies):` for consistency.

**Changes to `grammar.py`**:
1. Replace `TRIGGER_EVENT` and `REPLACEMENT_TYPE` terminals with single `GAME_EVENT`
2. Update `triggered_prop` and `replacement_prop` rules to use `GAME_EVENT`
3. Keep `REPLACEMENT_SCOPE` (`"self" | "any"`) unchanged — it's orthogonal

**Changes to `parser.py`**:
1. `triggered_prop()` — no change needed (already reads event as string)
2. `replacement_prop()` — apply alias mapping so `"die"` → `"dies"` etc.
3. Update `_parse_trigger_event` mapping in `triggers.py` to also accept the replacement-style names as aliases

**DSL test updates** (`tests/test_dsl.py`, `test_dsl_phase2.py`, `test_dsl_phase3.py`):
- Verify `when(dies):` and `replace(dies):` both parse correctly
- Verify old spelling `replace(die):` still works via alias
- Add test for new unified event names in both trigger and replacement contexts

### Step 6: Add backward-compat aliases

Keep `TriggerEvent` and `ReplacementType` as thin aliases that map to `GameEvent`:

```python
# In triggers.py
from mtg_engine.core.events import GameEvent

# TriggerEvent is now an alias — existing card definitions using
# string trigger names ("enters_battlefield", "dies", etc.) still work
# because _parse_trigger_event maps strings → GameEvent
TriggerEvent = GameEvent
```

```python
# In replacement_effects.py
from mtg_engine.core.events import GameEvent

# ReplacementType kept as-is internally but mapped from GameEvent
# by EventBus — no changes needed to ReplacementEffect dataclass
```

This means existing tests and card definitions work unchanged.

### Step 7: Update tests

- Run full test suite after each step
- Fix any import changes
- Add new tests for `EventBus` in `tests/test_events.py`:
  - Test that emitting a replaceable event checks replacements first
  - Test that emitting a triggerable event queues triggers
  - Test that prevented events don't queue triggers
  - Test typed event data round-trips through `.to_dict()` / `.from_dict()`
- Add DSL grammar tests for unified `GAME_EVENT` terminal

### Step 8: Update documentation

- Update `CLAUDE.md` "What's Already Implemented" section
- Update `docs/GAP_ANALYSIS.md` if applicable
- Update `CLAUDE.md` "Key Patterns" to document `event_bus.emit()` as the canonical way to fire events

## Migration Strategy

This is designed as a **non-breaking, incremental refactor**:

1. Create `events.py` with `GameEvent`, data classes, and `EventBus` — **no existing code changes yet**
2. Wire `EventBus` into `GameState` — still no behavior change
3. Refactor emit sites **one at a time**, running tests after each
4. Once all sites use `EventBus`, the old direct `check_triggers()` / `check_replacement()` calls are gone from game code (they still exist on the managers, used internally by `EventBus`)

## What This Enables

After this refactor, adding Prowess is just:
```python
triggered_abilities=[{
    "trigger": "cast",
    "source": {"relation": "you", "card_type": "noncreature"},
    "effects": [{"type": "pump", "power": 1, "toughness": 1, "duration": "end_of_turn"}]
}]
```

No new event types, no custom wiring, no hand-built dicts.

## Files Changed

| File | Change |
|------|--------|
| `mtg_engine/core/events.py` | **NEW** — `GameEvent` enum, typed event data classes, `EventBus` |
| `mtg_engine/core/game_state.py` | Add `event_bus` to `__init__`, refactor `move_card()` and `check_state_based_actions()` emit sites |
| `mtg_engine/core/game.py` | Refactor all emit sites in `draw_card()`, `play_land()`, `cast_spell()`, `_resolve_effect()`, `declare_attackers()`, `_apply_damage()` |
| `mtg_engine/core/triggers.py` | `TriggerEvent` becomes alias for `GameEvent`, `_parse_trigger_event` maps to `GameEvent` |
| `mtg_engine/core/replacement_effects.py` | Add `_REPLACEMENT_TO_EVENT` mapping, no structural changes |
| `mtg_engine/dsl/grammar.py` | Unify `TRIGGER_EVENT` + `REPLACEMENT_TYPE` → single `GAME_EVENT` terminal |
| `mtg_engine/dsl/parser.py` | Add replacement name aliases in `replacement_prop()`, use unified event names |
| `tests/test_events.py` | **NEW** — tests for `EventBus`, typed event data |
| `tests/test_dsl.py` | Add tests for unified grammar event names |
| `cards/sample.mtg` | Update any replacement definitions to use new spelling (optional, aliases handle old) |
| `CLAUDE.md` | Update docs |
