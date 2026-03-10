# Project: MTG Rules Engine

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
