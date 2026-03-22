# MTG Rules Engine — Gap Analysis & Implementation Roadmap

Based on comprehensive research of the MTG Comprehensive Rules (CR, Feb 2026),
this document identifies what our engine currently handles, what's missing, and
what mechanics need to be implemented to support custom card design and testing.

---

## 0. PROGRESS SUMMARY

### What Has Been Implemented

The following features have been built across Phases 1–4:

**Card Types & Type System**
- All seven core card types: Creature, Instant, Sorcery, Enchantment, Artifact, Planeswalker, Land
- Kindred type (formerly Tribal)
- Multi-type cards (e.g., "Artifact Creature", "Enchantment Creature")
- Multiple subtypes per card

**Keywords (Evergreen)**
- Combat: Flying, Reach, First Strike, Double Strike, Trample, Vigilance, Menace, Defender
- Static: Deathtouch, Lifelink, Haste, Hexproof, Shroud, Indestructible, Flash
- Triggered: Ward {cost} (with mana payment enforcement)
- Protection from X (targeting, blocking, damage prevention, enchant/equip checks)

**Keywords (Set Mechanics)**
- Morph / Disguise / Cloak (face-down casting, turning face-up, ward on disguise)
- Transform / DFCs (day/night, disturb, meld)
- Adventure (cast adventure half, exile, cast creature from exile)

**Stack & Spells**
- cast_spell flow with mana payment
- LIFO stack with resolution
- On-cast triggers
- Target validation during casting (hexproof, shroud, protection, ward cost)
- Target legality on resolution — fizzle if all targets illegal (CR 608.2b)
- Activated abilities on the stack via AbilityOnStack
- Mana abilities bypass the stack

**Triggered Abilities**
- ETB triggers with composable source filters (by card type, controller, name)
- Structured trigger conditions (e.g., "when a creature an opponent controls ETBs")
- Auto-placement of triggers on the stack
- Death triggers (DIES), LTB triggers (LEAVES_BATTLEFIELD)
- Combat triggers (ATTACKS, BLOCKS, BECOMES_BLOCKED, DEALS_COMBAT_DAMAGE, DEALS_COMBAT_DAMAGE_TO_PLAYER)
- Upkeep triggers (BEGIN_UPKEEP)
- Zone change triggers (ENTERS_GRAVEYARD, IS_EXILED, ENTERS_HAND, PUT_ON_TOP_LIBRARY, PUT_ON_BOTTOM_LIBRARY)

**Replacement Effects**
- Full ReplacementEffectManager with layering per CR 614
- Types: DAMAGE, DRAW, ENTER_BATTLEFIELD, DIE, DISCARD, COUNTER_PLACED, LIFE_GAIN, ZONE_CHANGE
- ETB replacement effects (enters tapped, enters with counters)
- Die replacement effects ("if ~ would die, instead...")
- Centralized EventBus dispatches all events through unified GameEvent enum, routing to both trigger and replacement managers

**Continuous Effects & Layer System**
- Full 7-layer system: COPY, CONTROL, TEXT, TYPE, COLOR, ABILITY, POWER_TOUGHNESS
- Layer 7 sublayers (7a–7e): characteristic-defining, set P/T, modifications, counters, switching
- Timestamp ordering within layers
- Anthem effects, keyword granting/removing

**Auras & Equipment**
- Aura attachment (can_enchant) separated from targeting restrictions
- Auras attach without targeting when not cast (e.g., moved onto battlefield)
- Protection-based state-based action: auras fall off if protection gained
- Equipment attachment and fall-off SBA

**Effects**
- Damage, destroy, draw, gain life, lose life, counter, tap, untap
- Create token, pump (+N/+N until end of turn), bounce, exile

**Mana System**
- 5 colors + colorless, ManaCost parsing, ManaPool
- Mana payment during cast_spell
- Mana abilities on lands (bypass the stack)

**Format Support**
- Format legality validation (Standard, Modern, Legacy, Vintage, Pioneer, Pauper, Commander)
- Deck size and copy-count rules per format
- Sideboard support
- Commander color identity validation

**Game Rules**
- Full turn loop with automatic phase/step progression (advance_step, advance_turn)
- Priority system with pass_priority() and players_passed tracking
- State-based actions: life ≤ 0, toughness ≤ 0, lethal damage, 0 loyalty, legend rule, counter cancellation, poison 10+, token cease-to-exist, aura/equipment fall-off, saga sacrifice, battle 0 defense
- Full combat system (declare attackers/blockers, first strike/double strike damage, trample, deathtouch, lifelink, vigilance, menace, flying/reach, protection)
- Cleanup step: discard to hand size, clear damage, clear end-of-turn effects, empty mana pools
- Zone management (hand, library, battlefield, graveyard, exile, stack, command)
- Sagas: ETB setup, lore counter advancement, chapter triggers, sacrifice SBA

**Test Coverage**
- 611 tests covering all implemented features
- Game-level integration tests for ward payment, hexproof blocking, protection targeting, saga lifecycle

---

## 1. CARD TYPES — Gaps

### Currently Implemented
- Creature, Instant, Sorcery, Enchantment, Artifact, Planeswalker, Land
- Kindred (formerly Tribal) ✅
- Multi-type cards ✅
- Multiple subtypes ✅

### Missing Card Types
- **Battle** (CR 310) — permanents with defense counters, introduced in March of the Machine
- ~~Kindred (CR 308)~~ ✅ Implemented
- **Dungeon** (CR 309) — placed in command zone, ventured into

### Missing Supertypes
- **World** — subject to the world rule (if 2+ world permanents exist, keep newest)
- **Ongoing** — only on Archenemy scheme cards (low priority)

### Remaining Type-Line Features
- ~~Multi-type cards~~ ✅ Implemented
- ~~Multiple subtypes~~ ✅ Implemented

### Artifact Subtypes Needed
- Equipment, Vehicle, Food, Treasure, Clue, Blood, Map, Powerstone, Incubator, Gold, Junk

### Enchantment Subtypes Needed
- Aura, Saga, Class, Curse, Case, Room, Role, Background, Shrine, Rune, Cartouche

### Land Subtypes Needed
- Basic land types: Plains, Island, Swamp, Mountain, Forest (with intrinsic mana abilities)
- Non-basic: Cave, Desert, Gate, Lair, Locus, Mine, Power-Plant, Tower, Urza's

### Spell Subtypes Needed (Instant/Sorcery)
- Adventure, Arcane, Lesson, Trap, Chorus, Omen

---

## 2. KEYWORD ABILITIES — Full Implementation List

### Priority 1: Evergreen Keywords (appear in every set)

These MUST be in the engine for realistic card testing:

| Keyword | Type | Status | Engine Requirement |
|---------|------|--------|-------------------|
| **Flying** | Evasion | ✅ | Can only be blocked by creatures with flying or reach |
| **Reach** | Static | ✅ | Can block creatures with flying |
| **First Strike** | Combat | ✅ | Deals damage in first combat damage step |
| **Double Strike** | Combat | ✅ | Deals damage in both first strike and normal combat damage steps |
| **Deathtouch** | Static | ✅ | Any amount of damage this deals to a creature is lethal |
| **Trample** | Combat | ✅ | Excess combat damage carries over to defending player/battle |
| **Lifelink** | Static | ✅ | Damage dealt also causes controller to gain that much life |
| **Vigilance** | Static | ✅ | Attacking doesn't cause this creature to tap |
| **Haste** | Static | ✅ | Can attack and use tap abilities the turn it enters |
| **Hexproof** | Static | ✅ | Can't be targeted by opponents' spells/abilities |
| **Menace** | Evasion | ✅ | Can only be blocked by 2+ creatures |
| **Defender** | Static | ✅ | Can't attack |
| **Flash** | Static | ✅ | Can be cast any time you could cast an instant |
| **Indestructible** | Static | ✅ | Can't be destroyed by damage or "destroy" effects |
| **Ward {cost}** | Triggered | ✅ | When targeted by opponent, counter unless they pay {cost} |
| **Protection (from X)** | Static | ✅ | Can't be damaged/enchanted/equipped/blocked/targeted by X |

All evergreen keywords are implemented.

### Priority 2: Deciduous Keywords (frequent, not every set)

| Keyword | Type | Engine Requirement |
|---------|------|-------------------|
| **Cycling {cost}** | Activated | ✅ Discard this, pay cost, draw a card |
| **Kicker {cost}** | Static/Trigger | ✅ Optional additional cost when casting for enhanced effect |
| **Flashback {cost}** | Static | ✅ Can be cast from graveyard for flashback cost, then exiled |
| **Equip {cost}** | Activated | Attach equipment to target creature you control |
| **Prowess** | Triggered | ✅ Whenever you cast a noncreature spell, +1/+1 until end of turn |
| **Surveil N** | Keyword action | Look at top N cards, put any in graveyard, rest back on top |
| **Landfall** | Ability word | Trigger: whenever a land enters under your control |
| **Scry N** | Keyword action | Look at top N, put any on bottom in any order, rest on top |
| **Mill N** | Keyword action | Put top N cards from library into graveyard |
| **Crew N** | Activated | Tap creatures with total power N+ to turn Vehicle into creature |
| **Investigate** | Keyword action | Create a Clue artifact token |
| **Treasure tokens** | Token creation | Artifact token with "Sacrifice: add one mana of any color" |

### Priority 3: Popular Set Mechanics

| Keyword | Type | Description |
|---------|------|-------------|
| **Adventure** | Alternate casting | ✅ Cast the adventure spell, exile, then cast creature from exile |
| **Sagas** | Enchantment | ✅ Lore counters, chapter abilities, sacrifice SBA, game engine integration |
| **Transform / DFCs** | Card layout | ✅ Flip between two faces on condition (day/night, disturb, meld) |
| **Mutate** | Alternate casting | Merge with creature, combined P/T and abilities |
| **Cascade** | Triggered | Exile cards until CMC less, cast free, put rest on bottom |
| **Convoke** | Static | Tap creatures to help pay for spell |
| **Delve** | Static | Exile cards from graveyard to pay generic mana |
| **Affinity (for X)** | Static | Costs {1} less for each X you control |
| **Annihilator N** | Triggered | Defending player sacrifices N permanents |
| **Morph / Disguise** | Alternate casting | ✅ Cast face-down as 2/2 for {3}, flip up for morph cost (ward on disguise) |
| **Bestow** | Alternate casting | Cast as Aura or as creature |
| **Dash** | Alternate casting | Cast for dash cost, gains haste, returns to hand at end |
| **Emerge** | Alternate casting | Sacrifice creature to reduce cost |
| **Enlist** | Combat | Tap non-attacking creature to add its power |
| **Escape** | Graveyard | Cast from graveyard, exile cards as additional cost |
| **Eternalize** | Activated | Exile from graveyard to create 4/4 token copy |
| **Evoke** | Alternate casting | Cast for evoke cost, sacrifice on ETB |
| **Exploit** | Triggered | On ETB, may sacrifice a creature |
| **Fabricate N** | Triggered | On ETB, choose +1/+1 counters or create 1/1 Servo tokens |
| **Frenzy** | Triggered | Whenever unblocked, gets +1/+0 until end of turn |
| **Hideaway** | Triggered/Activated | Exile cards face-down, cast later when condition met |
| **Ninjutsu** | Activated | Swap from hand with unblocked attacker |
| **Persist** | Triggered | Returns from graveyard with -1/-1 counter if didn't have one |
| **Populate** | Keyword action | Create copy of a creature token you control |
| **Proliferate** | Keyword action | Choose any permanents/players with counters, add one of each |
| **Raid** | Ability word | Bonus if you attacked this turn |
| **Rebound** | Triggered | Cast again from exile next upkeep |
| **Spectacle {cost}** | Alternate casting | Cast for spectacle cost if opponent lost life |
| **Splice onto Arcane** | Static | Copy spliced spell's text onto Arcane host spell |
| **Suspend N** | Special | Exile with time counters, remove one each upkeep, cast at 0 |
| **Toxic N** | Static | Damage to player also gives N poison counters |
| **Undying** | Triggered | Returns from graveyard with +1/+1 counter if didn't have one |
| **Unearth** | Activated | Return from graveyard, gains haste, exile at end of turn |
| **Wither** | Static | Damage to creatures is dealt as -1/-1 counters |
| **Infect** | Static | Damage to creatures as -1/-1 counters, to players as poison |
| **Exalted** | Triggered | Whenever a creature you control attacks alone, +1/+1 |
| **Embalm** | Activated | Exile from graveyard, create white token copy |

### Priority 4: Retired/Historic Keywords (support for older cards)

| Keyword | Replaced By | Description |
|---------|-------------|-------------|
| **Fear** | Menace/Intimidate | Only blocked by black or artifact creatures |
| **Intimidate** | Menace | Only blocked by creatures sharing a color or artifacts |
| **Shroud** | Hexproof | Can't be targeted by ANY spells/abilities (including own) |
| **Regenerate** | Indestructible | "Regeneration shield" prevents next destruction |
| **Banding** | N/A | Complex blocking/damage assignment grouping |
| **Landwalk** | N/A | Unblockable if defending player controls that land type |
| **Phasing** | Deciduous | Phases out/in, treated as doesn't exist while phased out |
| **Flanking** | N/A | Blockers without flanking get -1/-1 |
| **Shadow** | N/A | Can only block/be blocked by shadow creatures |
| **Horsemanship** | N/A | Can only be blocked by creatures with horsemanship |
| **Cumulative Upkeep** | N/A | Increasing cost each upkeep |

---

## 3. GAME RULES — Missing Engine Features

### 3a. Turn Structure — ✅ MOSTLY COMPLETE

**Implemented**:
- ✅ Full TURN_STRUCTURE with automatic phase/step progression (advance_step, advance_turn)
- ✅ Skip draw on first player's first turn
- ✅ Cleanup step: discard to hand size (7), clear damage, clear end-of-turn effects, empty mana pools
- ✅ Untap step, draw step, main phases, combat phases

**Remaining**:
- Cleanup repeats if SBAs trigger or abilities trigger during it
- Extra combat phases (from cards like Aggravated Assault)
- Extra turn tracking (Time Walk effects)
- Phasing happens during untap, before untapping

### 3b. Priority System — ✅ MOSTLY COMPLETE

**Implemented**:
- ✅ priority_player_index with pass_priority() and players_passed tracking
- ✅ Active player gets priority first
- ✅ SBAs checked before priority is granted (in run_step and resolve_top_of_stack)
- ✅ Triggered abilities go on stack before priority

**Remaining**:
- Players can hold priority (cast in response to own spell)
- No priority in untap or cleanup (unless triggers fire) — not enforced

### 3c. The Stack — ✅ MOSTLY COMPLETE

**Implemented**:
- ✅ LIFO stack with cast_spell flow (mana payment, target validation, ward cost)
- ✅ Triggered abilities auto-placed on stack
- ✅ Activated abilities on stack (AbilityOnStack)
- ✅ On-cast triggers
- ✅ Mana abilities bypass the stack (tap_land_for_mana)
- ✅ Target legality on resolution — fizzle if all targets illegal (CR 608.2b)

**Remaining**:
- Full casting sequence (CR 601): announce → choose modes → choose targets → determine costs → activate mana abilities → pay costs → spell becomes cast
- Split second (nothing else can go on stack while this resolves)
- Copy spells on the stack (Fork, Twincast effects)
- ~~Alternative costs / additional costs~~ ✅ (kicker, flashback)
- ~~X spells (X = 0 everywhere except stack)~~ ✅ (x_value on CardInstance, cast_spell x_value param)

### 3d. State-Based Actions — ✅ COMPLETE

All major SBAs from CR 704.5 are implemented in `GameState.check_state_based_actions()`:

- ✅ CR 704.5a: Player with 0 or less life loses
- ✅ CR 704.5b: Creature with 0 or less toughness goes to graveyard
- ✅ CR 704.5c: Creature with lethal damage goes to graveyard (respects indestructible)
- ✅ CR 704.5c: Player with 10+ poison counters loses
- ✅ CR 704.5d: Tokens not on the battlefield cease to exist
- ✅ CR 704.5i: Planeswalker with 0 loyalty goes to graveyard
- ✅ CR 704.5j: Legend rule (keep newest, rest to graveyard)
- ✅ CR 704.5m: Aura not attached to legal object goes to graveyard (including protection)
- ✅ CR 704.5n: +1/+1 and -1/-1 counters cancel each other out
- ✅ CR 704.5s: Battle with 0 defense counters is exiled
- ✅ CR 704.5t: Saga with final chapter counter is sacrificed
- ✅ Equipment fall-off handled via check_equipment_fall_off()
- ✅ Dies triggers fire for creatures that die during SBAs

**Remaining**:
- A player who attempted to draw from empty library loses (tracked in draw_card but not as SBA)
- Non-aura attached permanents become unattached if target becomes illegal

### 3e. Combat System — ✅ COMPLETE

Full combat system implemented:

- ✅ Beginning of combat, declare attackers, declare blockers, combat damage, end of combat steps
- ✅ Declare attackers: untapped creatures, summoning sickness (unless haste), defender can't attack, tap on attack (unless vigilance)
- ✅ Declare blockers: validate_blockers, menace (must block with 2+), flying/reach, protection
- ✅ First strike / double strike damage steps (separate phases)
- ✅ Trample: excess damage to defending player (considers deathtouch for lethal calculation)
- ✅ Deathtouch: 1 damage = lethal for assignment
- ✅ Lifelink: controller gains life equal to damage dealt
- ✅ Combat triggers: ATTACKS, BLOCKS, BECOMES_BLOCKED, DEALS_COMBAT_DAMAGE, DEALS_COMBAT_DAMAGE_TO_PLAYER
- ✅ SBAs checked after first strike and regular combat damage

**Remaining**:
- Must-block effects (e.g., Lure)
- Attacking planeswalkers/battles (currently only attacks players)

### 3f. Zone Rules — ✅ MOSTLY COMPLETE

**Implemented**:
- ✅ Zone tracking on CardInstance with move_card() as central zone-change handler
- ✅ Zone change triggers: ETB, DIES, LEAVES_BATTLEFIELD, ENTERS_GRAVEYARD, IS_EXILED, ENTERS_HAND, PUT_ON_TOP_LIBRARY, PUT_ON_BOTTOM_LIBRARY
- ✅ Tokens cease to exist when they leave the battlefield (SBA)
- ✅ Face-down cards (morph/disguise/cloak)

**Remaining**:
- Zone-change = new object rule (CR 400.7): card moving zones becomes a new object with no memory of previous zone
- Graveyard order matters (some formats)
- Library order matters (no peeking)
- Face-down cards in exile
- Phased-out permanents (treated as non-existent)

### 3g. Mana System — Partially Complete

**Implemented**:
- ✅ 5 colors + colorless, ManaCost parsing, ManaPool
- ✅ Mana payment during cast_spell
- ✅ Mana abilities on lands (bypass the stack)
- ✅ Color identity for Commander format

**Remaining**:
- ~~**Hybrid mana** (e.g., {R/G} — pay with either red or green)~~ ✅ Parsed, payable, integrated
- ~~**Phyrexian mana** (e.g., {R/P} — pay R or 2 life)~~ ✅ Life payment via cast_spell phyrexian_life_pay
- **Snow mana** ({S} — paid with mana from a snow source)
- **Generic vs Colorless distinction**: {1} is generic (any color), {C} specifically needs colorless
- ~~**X costs**: variable mana costs~~ ✅
- **Alternative costs**: Force of Will (exile blue card + 1 life), overload, etc.
- **Additional costs**: kicker, buyback, sacrificing creatures, etc.
- **Cost reduction**: affinity, convoke, delve
- **Mana produced by non-land sources** (e.g., mana dorks, artifacts)

### 3h. Targeting System — ✅ MOSTLY COMPLETE

**Implemented**:
- ✅ Target validation during cast_spell (hexproof, shroud, protection, ward cost)
- ✅ Target legality on resolution: all-illegal targets causes fizzle (CR 608.2b), partial-legal resolves for legal ones
- ✅ Hexproof/Shroud/Protection prevent targeting
- ✅ Ward triggered ability when targeted, counter if cost not paid

**Remaining**:
- **Target type validation**: legal target types (creature, player, planeswalker, any target, etc.)
- **"Each" vs "target"**: "each opponent" doesn't target
- **Same-target restrictions**: "target creature" and "another target creature"

### 3i. Continuous Effects & Layer System — ✅ IMPLEMENTED

Full 7-layer system implemented in `ContinuousEffectManager`:

1. ✅ **Layer 1 (COPY)**: Copy effects
2. ✅ **Layer 2 (CONTROL)**: Control-changing effects
3. ✅ **Layer 3 (TEXT)**: Text-changing effects
4. ✅ **Layer 4 (TYPE)**: Type-changing effects
5. ✅ **Layer 5 (COLOR)**: Color-changing effects
6. ✅ **Layer 6 (ABILITY)**: Ability-adding/removing effects
7. ✅ **Layer 7 (POWER_TOUGHNESS)**: With PTSublayer for 7a–7e (characteristic-defining, set P/T, modifications, counters, switching)

Effects applied in **timestamp order** within each layer.

**Remaining**:
- Dependency system (one effect depending on another within the same layer)
- Comprehensive testing of interactions between layers

### 3j. Replacement Effects — ✅ IMPLEMENTED

Full `ReplacementEffectManager` with layering per CR 614:

- ✅ DAMAGE replacement (prevention effects, damage redirection)
- ✅ DRAW replacement (e.g., "if you would draw, instead...")
- ✅ ENTER_BATTLEFIELD replacement (enters tapped, enters with counters)
- ✅ DIE replacement ("if ~ would die, instead...")
- ✅ DISCARD replacement
- ✅ COUNTER_PLACED replacement
- ✅ LIFE_GAIN replacement
- ✅ ZONE_CHANGE replacement

**Remaining**:
- CR 616.1 ordering when multiple replacement effects apply to same event
- "Can't be countered" as a replacement/prevention effect

### 3k. Triggered Abilities — ✅ MOSTLY COMPLETE

**Implemented**:
- ✅ ETB triggers with composable source filters (card type, controller, name)
- ✅ On-cast triggers
- ✅ Death triggers (DIES)
- ✅ LTB triggers (LEAVES_BATTLEFIELD)
- ✅ Combat triggers (ATTACKS, BLOCKS, BECOMES_BLOCKED, DEALS_COMBAT_DAMAGE, DEALS_COMBAT_DAMAGE_TO_PLAYER)
- ✅ Upkeep triggers (BEGIN_UPKEEP)
- ✅ Zone change triggers (ENTERS_GRAVEYARD, IS_EXILED, ENTERS_HAND, PUT_ON_TOP_LIBRARY, PUT_ON_BOTTOM_LIBRARY)
- ✅ Auto-placement on stack via put_triggers_on_stack()

**Remaining**:
- Trigger stacking order (APNAP: active player's triggers first)
- "If" clause checking on resolution
- Reflexive triggers ("when you do")

---

## 4. DSL GRAMMAR — Expansion Needed

### Currently Supported
- Basic card properties (name, type, cost, P/T, subtypes, rules text)
- Effects: damage, destroy, draw, gain_life, lose_life, counter, tap, create_token
- Targets: target(type), self, each_opponent, all(type)
- **LLM-powered rules translation**: Claude API translates natural language rules text → validated effect dicts (with regex fallback when no API key or validation failure)

### Missing DSL Features
- **Keywords**: `keywords: flying, lifelink, first_strike`
- **Multiple effects per card**: effect chains
- **Triggered abilities**: `when(enters_battlefield): effect`
- **Activated abilities**: `activate(cost): effect`
- **Static abilities**: `static: effect_while_on_battlefield`
- **Mana abilities**: `tap: add({G})`
- **Conditional effects**: `if(condition): effect`
- **Modal spells**: `choose(1, [effect1, effect2, effect3])`
- **X costs**: `cost: {X}{R}` with `damage(target(any_target), X)`
- **Kicker/Additional costs**: `kicker({2}): additional_effect`
- **Alternative costs**: `flashback({cost})`, `evoke({cost})`
- **Equipment/Aura attachment**: `enchant(creature)`, `equip({cost})`
- **Planeswalker loyalty abilities**: `+1: effect`, `-3: effect`, `-8: effect`
- **Sagas**: `chapter(1): effect`, `chapter(2): effect`
- **Token definitions**: more detailed token properties
- **Multi-type cards**: `type: Artifact Creature`
- **Multiple subtypes**: `subtype: Human Wizard`
- **Color indicators** for DFCs without mana costs

---

## 5. IMPLEMENTATION PRIORITY ROADMAP

### Phase 1: Core Rules (Foundation) — ✅ COMPLETE
1. ✅ Full turn loop with automatic phase/step progression
2. ✅ Priority system with passing
3. ✅ Combat system (declare attackers/blockers, damage)
4. ✅ Evergreen keywords (flying, first strike, deathtouch, trample, lifelink, etc.)
5. ✅ Complete state-based actions (basic set)
6. ✅ Basic triggered abilities (ETB triggers with source filters)

### Phase 2: Rich Card Support — ✅ COMPLETE
7. ✅ Expanded DSL with keywords, triggered/activated abilities
8. ✅ Equipment and Aura attachment
9. ✅ Planeswalker loyalty abilities
10. ✅ Token generation and management
11. ✅ Mana abilities (tap lands for mana)
12. ✅ Additional costs (kicker) and alternative costs (flashback)
13. ✅ Continuous effects (basic layer system for P/T modifications)

### Phase 3: Advanced Mechanics — ✅ MOSTLY COMPLETE
14. ✅ Full layer system (7 layers with sublayers, timestamp ordering)
15. ✅ Replacement effects (DAMAGE, DRAW, ETB, DIE, DISCARD, COUNTER_PLACED, LIFE_GAIN, ZONE_CHANGE)
16. ~~Hybrid/Phyrexian/Snow mana~~ ✅ (hybrid and Phyrexian implemented; snow mana parsed but not enforced)
17. ~~X spells~~ ✅
18. Copy effects — not yet
19. ✅ Face-down cards (morph, disguise, cloak)
20. ✅ DFCs and transform (day/night, disturb, meld)
21. ✅ Sagas (ETB setup, lore counters, chapter triggers, sacrifice SBA) and Class enchantments (level-up system)
22. ✅ Adventure cards

### Phase 4: Format Support — ✅ COMPLETE
23. ✅ Commander rules (color identity, command zone, commander tax)
24. ✅ Poison counters / infect / toxic
25. ✅ Multiplayer (3+ players, APNAP)
26. ✅ Sideboard / "outside the game" (Wishes, Lessons)
27. Battle cards — not yet

### Phase 5: Next Work (Suggested)

These are the highest-impact items remaining, in recommended priority order:

1. ~~**Death / LTB triggers**~~ ✅ — DIES, LEAVES_BATTLEFIELD, and many other zone-change triggers implemented
2. ~~**Legend rule SBA**~~ ✅ — CR 704.5j implemented
3. ~~**Target legality on resolution**~~ ✅ — fizzle on all-illegal targets (CR 608.2b)
4. ~~**Replacement effects**~~ ✅ — full ReplacementEffectManager with 8 replacement types
5. ~~**Full layer system**~~ ✅ — 7-layer ContinuousEffectManager with sublayers and timestamp ordering
6. ~~**Sagas**~~ ✅ — lore counters, chapter abilities, sacrifice SBA, game engine integration
7. ~~**Kicker / additional costs**~~ ✅ — optional extra costs when casting, kicker_effects appended
8. ~~**Flashback**~~ ✅ — cast from graveyard for flashback cost, exiled on resolution
9. ~~**X spells** — variable mana costs~~ ✅
10. ~~**Hybrid / Phyrexian mana** — {R/G} and {R/P} cost types~~ ✅
11. **Copy effects** — Fork, Twincast, Clone
12. ~~**Cycling** — discard to draw~~ ✅
13. ~~**Prowess** — noncreature spell trigger for +1/+1~~ ✅

---

## 6. ABILITY WORDS REFERENCE

Ability words have no rules meaning — they're flavor labels for trigger patterns.
The engine should recognize them in the DSL but treat them as annotations:

adamant, addendum, alliance, battalion, bloodrush, celebration, channel, chroma,
cohort, constellation, converge, council's dilemma, coven, delirium, descend 4,
descend 8, domain, eerie, eminence, enrage, fateful hour, fathomless descent,
ferocious, flurry, formidable, grandeur, hellbent, heroic, imprint, inspired,
join forces, kinship, landfall, lieutenant, magecraft, metalcraft, morbid,
pack tactics, paradox, parley, radiance, raid, rally, renew, revolt, secret council,
spell mastery, strive, survival, sweep, tempting offer, threshold, undergrowth,
valiant, vivid, void, will of the council
