# Project: MTG Rules Engine

## Workflow Rules
- **Documentation updates are mandatory**: When implementing a feature or fixing a bug, update ALL relevant docs:
  - `CLAUDE.md` — update "What's Already Implemented" and "Remaining Gaps" sections
  - `docs/GAP_ANALYSIS.md` — strike through completed items, update phase status
- **Track small tasks and future improvements**: Add discovered issues, tech debt, or small follow-ups to the "Future Improvements / Small Tasks" section below so they aren't lost between sessions.
- **Tests**: Always run `python -m pytest` after changes. Current count: 538 tests.
- **Commit style**: Imperative mood, explain "why" not "what". Include session link.

## Architecture
- **Core engine**: `mtg_engine/core/` — game loop (`game.py`), state (`game_state.py`), cards (`card.py`)
- **Stack system**: `AbilityOnStack` for triggered/activated abilities, `CardInstance` implements `Stackable` protocol for spells
- **SBAs**: All in `GameState.check_state_based_actions()` in `game_state.py`
- **Tests**: `tests/` directory, run with `python -m pytest`

## What's Already Implemented
- **SBAs**: lethal damage, 0 toughness, 0 life, poison, planeswalker 0 loyalty, legend rule, counter cancellation (+1/+1 vs -1/-1), battle 0 defense, token cease-to-exist, aura attachment legality, saga sacrifice
- **Sagas**: Full lifecycle — ETB setup with lore counter + chapter 1 trigger, lore advancement after draw step, chapter abilities on stack, sacrifice SBA. Card definition uses `chapter_abilities` field on `Card`. Counter placement is explicit (separate from saga state setup) for future Doubling Season/Vorinclex hookability.
- **Classes**: Level-up system in `sagas.py` (shared module with sagas)
- **Combat**: Full combat with first strike, menace, trample, deathtouch, lifelink, vigilance, flying, reach, protection, ward
- **Replacement effects**: ETB modifications (enters tapped, enters with counters), die replacement, draw replacement
- **Continuous effects**: Anthem effects, keyword granting/removing
- **Equipment/Auras**: Attach, detach, protection-based falling off
- **Planeswalkers**: Loyalty abilities, uniqueness (legend rule covers this)
- **Adventure**: Cast as adventure, exile, cast from exile

## Key Patterns
- `move_card()` in `game_state.py` is the central zone-change method — handles all ETB logic (summoning sickness, planeswalker loyalty init, saga setup, replacement effects)
- `run_step()` calls `check_state_based_actions()` after each step's automatic actions
- `resolve_top_of_stack()` also calls `check_state_based_actions()` after resolution
- Saga lore advancement happens in `Game._advance_sagas()`, called from `step_draw()`
- Cards define abilities declaratively via dicts in `effects`, `triggered_abilities`, `activated_abilities`, `chapter_abilities`

## Remaining Gaps (Phase 5+)
See `docs/GAP_ANALYSIS.md` for full details. Key remaining items:
- Kicker/additional costs
- Flashback
- X spells
- Hybrid/Phyrexian mana
- Full 7-layer continuous effects system

## Future Improvements / Small Tasks
<!-- Add discovered issues, tech debt, and follow-ups here so they survive between sessions -->
- Route saga lore counter placement through a counter-modification system when Doubling Season / Vorinclex effects are implemented
- GAP_ANALYSIS.md section 3d (SBAs) is outdated — lists many SBAs as "missing" that are already implemented. Needs a cleanup pass to strike through completed items.
- GAP_ANALYSIS.md section 3e (combat) says "No combat implementation yet" but combat is fully implemented. Needs update.
- GAP_ANALYSIS.md sections 3j (replacement effects) and 3k (triggered abilities) understate what's implemented. Needs update.
- Test count in GAP_ANALYSIS.md says 457 but actual count is 538. Update when touching the file.
