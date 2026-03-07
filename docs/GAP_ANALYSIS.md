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

**Triggered Abilities**
- ETB triggers with composable source filters (by card type, controller, name)
- Structured trigger conditions (e.g., "when a creature an opponent controls ETBs")
- Auto-placement of triggers on the stack

**Auras & Equipment**
- Aura attachment (can_enchant) separated from targeting restrictions
- Auras attach without targeting when not cast (e.g., moved onto battlefield)
- Protection-based state-based action: auras fall off if protection gained
- Equipment attachment

**Effects**
- Damage, destroy, draw, gain life, lose life, counter, tap, untap
- Create token, pump (+N/+N until end of turn), bounce, exile
- Continuous effects (basic)

**Mana System**
- 5 colors + colorless, ManaCost parsing, ManaPool
- Mana payment during cast_spell
- Mana abilities on lands

**Format Support**
- Format legality validation (Standard, Modern, Legacy, Vintage, Pioneer, Pauper, Commander)
- Deck size and copy-count rules per format
- Sideboard support
- Commander color identity validation

**Game Rules**
- State-based actions: life ≤ 0, toughness ≤ 0, lethal damage
- Basic combat system (declare attackers/blockers, damage assignment)
- Priority player tracking
- Zone management (hand, library, battlefield, graveyard, exile, stack, command)

**Test Coverage**
- 457 tests covering all implemented features
- Game-level integration tests for ward payment, hexproof blocking, protection targeting

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
| **Cycling {cost}** | Activated | Discard this, pay cost, draw a card |
| **Kicker {cost}** | Static/Trigger | Optional additional cost when casting for enhanced effect |
| **Flashback {cost}** | Static | Can be cast from graveyard for flashback cost, then exiled |
| **Equip {cost}** | Activated | Attach equipment to target creature you control |
| **Prowess** | Triggered | Whenever you cast a noncreature spell, +1/+1 until end of turn |
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
| **Sagas** | Enchantment | Lore counters, chapter abilities trigger sequentially |
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

### 3a. Turn Structure Gaps

**Current**: Basic phase/step enum exists but no turn loop automation.

**Missing**:
- Automatic phase/step progression through the full turn
- Skip draw on first player's first turn (partially implemented)
- Cleanup step: discard to hand size (7), remove "until end of turn" effects, clear damage
- Cleanup repeats if SBAs trigger or abilities trigger during it
- Extra combat phases (from cards like Aggravated Assault)
- Extra turn tracking (Time Walk effects)
- Phasing happens during untap, before untapping

### 3b. Priority System

**Current**: `priority_player_index` exists but no passing logic.

**Missing**:
- Active player gets priority first (APNAP order)
- Priority passes around the table
- When all players pass with empty stack, phase/step advances
- When all pass with non-empty stack, top item resolves
- Players can hold priority (cast in response to own spell)
- SBAs checked before any player receives priority
- Triggered abilities go on stack before priority is granted
- No priority in untap or cleanup (unless triggers fire)

### 3c. The Stack — Partially Implemented

**Current**: LIFO stack with cast_spell flow (mana payment, target validation, ward cost enforcement). Triggered abilities auto-placed on stack. On-cast triggers supported.

**Remaining**:
- Full casting sequence (CR 601): announce → choose modes → choose targets → determine costs → activate mana abilities → pay costs → spell becomes cast
- Activated abilities on the stack (currently only spells and triggers)
- ~~Triggered abilities on the stack~~ ✅
- Mana abilities don't use the stack
- Split second (nothing else can go on stack while this resolves)
- Copy spells on the stack (Fork, Twincast effects)
- Alternative costs / additional costs
- X spells (X = 0 everywhere except stack)

### 3d. State-Based Actions — Missing

**Current**: Life ≤ 0, toughness ≤ 0, lethal damage.

**Missing** (full list from CR 704.5):
- Legend rule: if player controls 2+ legendary permanents with same name, choose one, rest go to graveyard
- Planeswalker loyalty: if 0 loyalty, goes to graveyard
- Aura: if not attached to legal object, goes to graveyard
- Equipment/Fortification: if attached to illegal permanent, becomes unattached
- +1/+1 and -1/-1 counters cancel each other out
- Token not on battlefield: ceases to exist
- Poison counters: player with 10+ poison counters loses
- A player who attempted to draw from empty library loses
- A creature with 0 toughness goes to graveyard (already have this, but verify)
- Sagas: sacrifice when final chapter has resolved and triggered ability has left stack
- Battle: exile when defense reaches 0
- Non-aura attached permanents become unattached if target becomes illegal

### 3e. Combat System — Major Gaps

**Current**: No combat implementation yet.

**Needed**:
- Beginning of combat step (triggers, priority)
- Declare attackers step:
  - Choose attacking creatures (must be untapped, no summoning sickness unless haste, no defender)
  - Tap attacking creatures (unless vigilance)
  - Attacking player declares which player/planeswalker/battle each attacker attacks
  - "Whenever attacks" triggers
- Declare blockers step:
  - Defending player assigns blockers
  - Each blocker must block a legal attacker
  - Menace: must be blocked by 2+ creatures
  - Flying: only blocked by flying/reach
  - Must-block effects (e.g., Lure)
  - "Whenever blocks" triggers
- Combat damage step:
  - First strike damage step (if any creature has first strike or double strike)
  - Regular damage step
  - Trample: assign lethal to blockers (considering deathtouch), rest to defending player
  - Deathtouch: 1 damage = lethal for assignment purposes
  - Lifelink: controller gains life equal to damage dealt
  - Multiple blockers: attacker assigns damage in order (Foundations update removed damage assignment order — attacker now freely divides)
- End of combat step (triggers, priority)

### 3f. Zone Rules — Missing

**Current**: Basic zone tracking on CardInstance.

**Missing**:
- Zone change triggers ("when enters the battlefield", "when dies", "when leaves")
- Zone-change = new object rule (CR 400.7): card moving zones becomes a new object with no memory of previous zone
- Graveyard order matters (some formats)
- Library order matters (no peeking)
- Face-down cards in exile
- Phased-out permanents (treated as non-existent)
- Tokens cease to exist when they leave the battlefield

### 3g. Mana System — Gaps

**Current**: 5 colors + colorless, ManaCost parsing, ManaPool.

**Missing**:
- **Hybrid mana** (e.g., {R/G} — pay with either red or green)
- **Phyrexian mana** (e.g., {R/P} — pay R or 2 life)
- **Snow mana** ({S} — paid with mana from a snow source)
- **Generic vs Colorless distinction**: {1} is generic (any color), {C} specifically needs colorless
- **Mana abilities**: lands tap for mana without using the stack
- **Color identity** for Commander format
- **X costs**: variable mana costs
- **Alternative costs**: Force of Will (exile blue card + 1 life), overload, etc.
- **Additional costs**: kicker, buyback, sacrificing creatures, etc.
- **Cost reduction**: affinity, convoke, delve
- **Mana produced by non-land sources** (e.g., mana dorks, artifacts)

### 3h. Targeting System — Partially Implemented

**Current**: Target validation during cast_spell enforces hexproof, shroud, protection, and ward cost payment. Game-level integration tests verify targeting restrictions.

**Remaining**:
- **Target validation**: legal target types (creature, player, planeswalker, any target, etc.)
- **Target legality on resolution**: if all targets illegal, spell is countered; if some illegal, resolve for legal ones
- ~~Hexproof/Shroud/Protection~~ ✅ prevent targeting (enforced during cast_spell)
- ~~Ward~~ ✅ triggered ability when targeted, counter if cost not paid
- **"Each" vs "target"**: "each opponent" doesn't target
- **Same-target restrictions**: "target creature" and "another target creature"

### 3i. Continuous Effects & Layer System

**Not implemented at all.** This is one of the most complex parts of the rules.

**The 7 Layers** (CR 613):
1. **Layer 1**: Copy effects (1a: copy, 1b: face-down status)
2. **Layer 2**: Control-changing effects
3. **Layer 3**: Text-changing effects
4. **Layer 4**: Type-changing effects
5. **Layer 5**: Color-changing effects
6. **Layer 6**: Ability-adding/removing effects
7. **Layer 7**: Power/toughness (7a: characteristic-defining, 7b: set P/T, 7c: modifications, 7d: counters, 7e: switching P/T)

Within each layer, effects are applied in **timestamp order** unless there's a **dependency** (one effect depends on another).

### 3j. Replacement Effects — Missing

- "Instead" / "If... would... instead" effects
- Enters-the-battlefield replacement effects (e.g., "enters with N counters")
- Prevention effects (prevent damage, can't be countered)
- One replacement effect per event
- CR 616.1 ordering when multiple replacement effects apply

### 3k. Triggered Abilities — Partially Implemented

**Current**: ETB triggers with composable source filters (card type, controller, name). Triggers auto-placed on stack. On-cast triggers supported.

**Remaining**:
- ~~ETB (enters the battlefield) triggers~~ ✅ (with composable source filters)
- ~~On-cast triggers~~ ✅
- LTB (leaves the battlefield) triggers
- Death triggers ("when this creature dies")
- Combat triggers
- Upkeep triggers
- Trigger stacking order (APNAP: active player's triggers first)
- "If" clause checking on resolution
- Reflexive triggers ("when you do")

---

## 4. DSL GRAMMAR — Expansion Needed

### Currently Supported
- Basic card properties (name, type, cost, P/T, subtypes, rules text)
- Effects: damage, destroy, draw, gain_life, lose_life, counter, tap, create_token
- Targets: target(type), self, each_opponent, all(type)

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
12. Alternative/additional costs (kicker, flashback) — partial
13. ✅ Continuous effects (basic layer system for P/T modifications)

### Phase 3: Advanced Mechanics — ✅ MOSTLY COMPLETE
14. Full layer system (7 layers) — not yet
15. Replacement effects — not yet
16. Hybrid/Phyrexian/Snow mana — not yet
17. X spells — not yet
18. Copy effects — not yet
19. ✅ Face-down cards (morph, disguise, cloak)
20. ✅ DFCs and transform (day/night, disturb, meld)
21. Sagas and Class enchantments — not yet
22. ✅ Adventure cards

### Phase 4: Format Support — ✅ COMPLETE
23. ✅ Commander rules (color identity, command zone, commander tax)
24. ✅ Poison counters / infect / toxic
25. ✅ Multiplayer (3+ players, APNAP)
26. ✅ Sideboard / "outside the game" (Wishes, Lessons)
27. Battle cards — not yet

### Phase 5: Next Work (Suggested)

These are the highest-impact items remaining, in recommended priority order:

1. **Death / LTB triggers** — "when this creature dies" and "when ~ leaves the battlefield" are among the most common trigger types in MTG
2. **Legend rule SBA** — if a player controls 2+ legendaries with the same name, keep one
3. **Target legality on resolution** — if all targets are illegal when a spell resolves, counter it
4. **Replacement effects** — "if ~ would die, instead..." and ETB replacement effects (enters with counters)
5. **Full layer system** — 7-layer continuous effect ordering for correct P/T and ability interactions
6. **Sagas** — lore counters and chapter abilities
7. **Kicker / additional costs** — optional extra costs when casting
8. **Flashback** — cast from graveyard for alternate cost, then exile
9. **X spells** — variable mana costs
10. **Hybrid / Phyrexian mana** — {R/G} and {R/P} cost types

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
