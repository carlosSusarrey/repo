# Project: MTG Rules Engine

## Workflow Rules
- **Documentation updates are mandatory**: When implementing a feature or fixing a bug, update ALL relevant docs:
  - `CLAUDE.md` — update "What's Already Implemented" and "Remaining Gaps" sections
  - `docs/GAP_ANALYSIS.md` — strike through completed items, update phase status
  - `README.md` — update "Implemented Mechanics" if the change adds a user-visible mechanic or major feature
- **Track small tasks and future improvements**: Add discovered issues, tech debt, or small follow-ups to the "Future Improvements / Small Tasks" section below so they aren't lost between sessions.
- **Tests**: Always run `python -m pytest` after changes. Current count: 798 tests.
- **Commit style**: Imperative mood, explain "why" not "what". Include session link.

## Architecture
- **Core engine**: `mtg_engine/core/` — game loop (`game.py`), state (`game_state.py`), cards (`card.py`)
- **Event system**: `mtg_engine/core/events.py` — unified `GameEvent` enum, typed event data classes, `EventBus` dispatcher
- **Stack system**: `AbilityOnStack` for triggered/activated abilities, `CardInstance` implements `Stackable` protocol for spells
- **SBAs**: All in `GameState.check_state_based_actions()` in `game_state.py`
- **DSL layer**: `mtg_engine/dsl/` — grammar (`grammar.py`), parser (`parser.py`), regex rules translator (`rules_parser.py`), LLM rules translator (`llm_rules_parser.py`)
- **Tests**: `tests/` directory, run with `python -m pytest`

## LLM Rules Translation (`llm_rules_parser.py`)

The LLM translator is the **primary** path for converting natural language MTG rules text into engine effect dicts. It replaces the regex-based `rules_parser.py` as the default, with regex as fallback.

### How it works
1. **`parser.py`** calls `translate_rules_text_llm()` when a card has `rules:` text but no explicit `effect:`/`keywords:`/`when():`/`activate():` definitions
2. **`llm_rules_parser.py`** sends the rules text to Claude with a system prompt containing the full effect schema, valid types, and 40 few-shot examples
3. Claude returns JSON matching the engine's effect dict format
4. **Validation layer** checks every effect type, target, trigger event, and keyword against `VALID_*` frozensets — rejects anything the engine doesn't support
5. **Normalization** converts keyword strings to `Keyword` enum values
6. If the LLM call fails (no API key, network error, invalid output), **falls back to regex parser** transparently

### Keeping the system prompt in sync — IMPORTANT
The system prompt is **auto-generated** from data structures, not hardcoded. The function `_build_system_prompt()` builds it at import time from:

| Data source | What it generates in the prompt |
|---|---|
| `VALID_EFFECT_TYPES` + `EFFECT_TYPE_DOCS` | "Effect types and their fields" section |
| `VALID_TARGET_KINDS` | Target dict `kind` values |
| `VALID_TARGET_TYPES` | Target dict `target_type` values |
| `VALID_CONTROLLER_QUALIFIERS` | Target dict `controller` values |
| `VALID_STATE_QUALIFIERS` | Target dict `state` values |
| `VALID_TRIGGER_EVENTS` | Triggered ability `trigger` values |
| `VALID_KEYWORDS` (from `KEYWORD_MAP`) | Keywords list |

**Sync tests** in `tests/test_llm_rules_parser.py::TestPromptSync` verify every `VALID_*` entry appears in both the docs mapping and the generated prompt. These tests **fail immediately** if anything drifts.

### How to add a new effect type
When adding a new effect type to the engine (e.g., `"untap"`):

1. **`game.py`**: Add handler in `_resolve_effect()` — `elif effect_type == "untap": ...`
2. **`llm_rules_parser.py`**: Add to **both**:
   - `VALID_EFFECT_TYPES` frozenset — `"untap"`
   - `EFFECT_TYPE_DOCS` dict — `"untap": "{type, target}"`
3. **`rules_parser.py`**: Add regex pattern to `_EFFECT_PATTERNS` (for offline fallback)
4. **`llm_rules_parser.py` examples**: Add an Input/Output example to the `_build_system_prompt()` f-string examples section
5. **Tests**: Add test in `test_rules_parser.py` and optionally `test_llm_rules_parser.py`

The system prompt auto-updates from steps 2. The sync tests catch it if you forget `EFFECT_TYPE_DOCS`.

### How to add a new target type, trigger event, keyword, or qualifier
Same pattern — add to the relevant `VALID_*` frozenset in `llm_rules_parser.py`. For keywords, add to `KEYWORD_MAP` in `keywords.py` (which `VALID_KEYWORDS` reads automatically). The prompt regenerates, sync tests verify.

### Configuration — LLM provider selection

The LLM provider is configured via environment variables. Supports Anthropic (cloud) and any OpenAI-compatible server (local LLMs).

**Anthropic (default):**
```bash
export LLM_PROVIDER=anthropic          # or just leave unset
export ANTHROPIC_API_KEY=sk-ant-...    # required
export LLM_MODEL=claude-sonnet-4-20250514  # optional, this is the default
```

**Local LLMs (Ollama, vLLM, llama.cpp, LM Studio, LocalAI, etc.):**
```bash
export LLM_PROVIDER=openai
export LLM_BASE_URL=http://localhost:11434/v1   # your local server's OpenAI-compatible endpoint
export LLM_API_KEY=not-needed                   # required by SDK but often ignored by local servers
export LLM_MODEL=llama3                         # model name your server knows
```

**Common local setups:**
| Server | LLM_BASE_URL | Notes |
|---|---|---|
| Ollama | `http://localhost:11434/v1` | Run `ollama serve` first |
| vLLM | `http://localhost:8000/v1` | `python -m vllm.entrypoints.openai.api_server` |
| llama.cpp | `http://localhost:8080/v1` | `./server -m model.gguf` |
| LM Studio | `http://localhost:1234/v1` | Start local server in UI |
| LocalAI | `http://localhost:8080/v1` | Follow LocalAI docs |

**Fallback behavior:** If no API key is set, or the LLM call fails, or validation rejects the output, the regex parser (`rules_parser.py`) handles it transparently. No configuration needed for offline-only use.

**Programmatic override:** `translate_rules_text_llm(rules_text, api_key="...", fallback=True)` — `api_key` overrides env vars, `fallback=False` disables regex fallback.

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
- **Rules text auto-translation**: `rules:` field auto-generates effects, keywords, triggers, and activated abilities. Primary translator is LLM-based (`llm_rules_parser.py`) — supports Anthropic (Claude) and any OpenAI-compatible server (Ollama, vLLM, llama.cpp, LM Studio, etc.) for local LLM inference. Falls back to regex-based parser (`rules_parser.py`) when no API key is set or LLM output fails validation. Skipped when explicit `effect:`/`keywords:`/`when():`/`activate():` are defined. Set `ANTHROPIC_API_KEY` env var to enable LLM translation.
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
