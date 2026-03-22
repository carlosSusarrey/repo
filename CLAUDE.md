# Project: MTG Rules Engine

## Workflow Rules
- **Documentation updates are mandatory**: When implementing a feature or fixing a bug, update ALL relevant docs:
  - `CLAUDE.md` — update "What's Already Implemented" and "Remaining Gaps" sections
  - `docs/GAP_ANALYSIS.md` — strike through completed items, update phase status
  - `README.md` — update "Implemented Mechanics" if the change adds a user-visible mechanic or major feature
- **Track small tasks and future improvements**: Add discovered issues, tech debt, or small follow-ups to the "Future Improvements / Small Tasks" section below so they aren't lost between sessions.
- **Tests**: Always run `python -m pytest` after changes. Current count: 789 tests.
- **Commit style**: Imperative mood, explain "why" not "what". Include session link.

## Architecture
- **Core engine**: `mtg_engine/core/` — game loop (`game.py`), state (`game_state.py`), cards (`card.py`)
- **Event system**: `mtg_engine/core/events.py` — unified `GameEvent` enum, typed event data classes, `EventBus` dispatcher
- **Stack system**: `AbilityOnStack` for triggered/activated abilities, `CardInstance` implements `Stackable` protocol for spells
- **SBAs**: All in `GameState.check_state_based_actions()` in `game_state.py`
- **Tests**: `tests/` directory, run with `python -m pytest`

## What's Already Implemented
- **SBAs**: lethal damage, 0 toughness, 0 life, poison, planeswalker 0 loyalty, legend rule, counter cancellation (+1/+1 vs -1/-1), battle 0 defense, token cease-to-exist, aura attachment legality, saga sacrifice
- **Sagas**: Full lifecycle — ETB setup with lore counter + chapter 1 trigger, lore advancement after draw step, chapter abilities on stack, sacrifice SBA. Card definition uses `chapter_abilities` field on `Card`. Counter placement is explicit (separate from saga state setup) for future Doubling Season/Vorinclex hookability.
- **Classes**: Level-up system in `sagas.py` (shared module with sagas)
- **Combat**: Full combat with first strike, menace, trample, deathtouch, lifelink, vigilance, flying, reach, protection, ward
- **Replacement effects**: ETB modifications (enters tapped, enters with counters), die replacement, draw replacement
- **Centralized event system**: Unified `GameEvent` enum + `EventBus` replaces scattered trigger/replacement emit sites. DSL grammar uses single `GAME_EVENT` terminal for both `when()` and `replace()` syntax.
- **Continuous effects**: Anthem effects, keyword granting/removing
- **Equipment/Auras**: Attach, detach, protection-based falling off
- **Planeswalkers**: Loyalty abilities, uniqueness (legend rule covers this)
- **Adventure**: Cast as adventure, exile, cast from exile
- **Kicker**: Optional additional cost (`kicker_cost` on Card), `kicker_effects` appended when kicked, `was_kicked` tracked on CardInstance
- **Flashback**: Cast from graveyard for `flashback_cost`, exiled on resolution, `cast_with_flashback` tracked on CardInstance
- **X spells**: Variable mana costs (`x_count` on ManaCost, `x_value` on CardInstance). `cast_spell(x_value=N)` adds N×x_count as generic mana. X=0 everywhere except the stack (CR 107.3b). `x_damage` effect uses stored `x_value`.
- **Hybrid mana**: `{W/U}` style costs parsed by ManaCost, payable with either color. Contributes both colors to color identity.
- **Phyrexian mana**: `{R/P}` style costs payable with mana or 2 life. `cast_spell(phyrexian_life_pay=[indices])` for life payment.
- **Cycling**: Activated ability — discard from hand, pay `cycling_cost`, draw a card. `activate_cycling()` in Game.
- **Prowess**: Triggered ability — whenever a noncreature spell is cast, each creature with prowess you control gets +1/+1 until EOT. Checked in `cast_spell`, creates `AbilityOnStack` entries.
- **Rules text auto-translation**: `rules:` field auto-generates effects, keywords, triggers, and activated abilities. Primary translator is LLM-based (`llm_rules_parser.py`) using Claude API — understands natural language rules text and produces validated effect dicts. Falls back to regex-based parser (`rules_parser.py`) when no API key is set or LLM output fails validation. Skipped when explicit `effect:`/`keywords:`/`when():`/`activate():` are defined. Set `ANTHROPIC_API_KEY` env var to enable LLM translation.
- **"May" (optional effects)**: DSL `may(effect)` and rules text "you may [effect]". Controller chooses whether to execute via `decision_callback` on `Game.__init__` (default: always accept). Declining is valid resolution (success=True, declined=True).
- **Sacrifice as cost**: DSL `activate(sacrifice(creature)): effect` or `activate({2}, sacrifice(land)): effect`. Rules text "Sacrifice a creature: draw a card". `Game.activate_ability()` method handles cost payment (tap + sacrifice) before putting ability on stack. Validates type match.
- **Conditional effects**: DSL `if_did(condition_effect, then_effect)` and rules text "If you do/did, [effect]". Condition is resolved first; then-effect fires only if condition succeeded and was not declined. Composes with `may` for "you may X. If you do, Y" patterns.
- **Copy spell**: DSL `copy_spell(self)` or `copy_spell(target_spell, new_targets)`. Rules text "copy this spell", "copy target spell". `AbilityOnStack.copy()` creates independent duplicate on stack with inherited targets. Self-copy and target-copy supported. `new_targets` invokes `target_callback` on `Game.__init__` (default: keep original targets) to allow retargeting.
- **Centralized filter vocabulary**: `filters.py` provides shared constants and matching logic for triggers, targets, and replacement effects. Controller qualifiers (`you`/`opponent`), state qualifiers (`attacking`/`blocking`/`tapped`/`untapped`), card type keywords, token status.
- **Web UI**: Flask app with card DSL editor, live preview, engine translation panel, example library (12 categories), and card schema reference.

## Key Patterns
- **EventBus**: `state.event_bus.emit()` / `emit_triggers_only()` / `emit_replacement_only()` is the canonical way to fire game events. All emit sites in `game.py` and `game_state.py` go through EventBus — never call `triggers.check_triggers()` or `replacement_effects.check_replacement()` directly from game code.
- `move_card()` in `game_state.py` is the central zone-change method — handles all ETB logic (summoning sickness, planeswalker loyalty init, saga setup, replacement effects)
- `run_step()` calls `check_state_based_actions()` after each step's automatic actions
- `resolve_top_of_stack()` also calls `check_state_based_actions()` after resolution
- Saga lore advancement happens in `Game._advance_sagas()`, called from `step_draw()`
- Cards define abilities declaratively via dicts in `effects`, `triggered_abilities`, `activated_abilities`, `chapter_abilities`
- **DSL grammar**: Uses unified `GAME_EVENT` terminal — same event names work in both `when(event):` (triggers) and `replace(event):` (replacements). Old replacement names (`die`, `enter_battlefield`, `draw`, `life_gain`) are accepted and auto-normalized to trigger-style (`dies`, `enters_battlefield`, `draw_card`, `gain_life`).
- **DSL target syntax**: `target(creature)`, `target(creature, opponent)`, `target(creature, attacking)`, `target(creature, opponent, attacking)`, `all(creature)`, `all(creature, attacking)`, `all(creature, opponent)`.

## Remaining Gaps (Phase 5+)
See `docs/GAP_ANALYSIS.md` for full details. Key remaining items:
- Copy effects: spell copying works (Fork), creature/permanent cloning (Clone) not yet implemented

## Future Improvements / Small Tasks
<!-- Add discovered issues, tech debt, and follow-ups here so they survive between sessions -->
- Replace `decision_callback` and `target_callback` (synchronous) with a queue-based decision system (`pending_decisions` on `GameState`) for async/UI integration when building interactive game clients
- `target_callback` does not validate that chosen targets are legal — add target legality checks for copied spells
- Route saga lore counter placement through a counter-modification system when Doubling Season / Vorinclex effects are implemented
- Layer system dependency resolution (effects within same layer that depend on each other) not yet implemented
- CR 616.1 ordering for multiple replacement effects applying to same event not yet implemented
- Must-block effects (e.g., Lure) not yet in combat
- Attacking planeswalkers/battles not yet supported (currently only attacks players)
- Cleanup step does not repeat if SBAs/triggers fire during it
