# MTG Rules Engine

A Magic: The Gathering rules engine for designing and testing custom cards. Define cards using a domain-specific language (DSL), simulate games, and see how mechanics interact.

## Features

- **Rules Engine**: Implements MTG game rules including phases, priority, the stack, and zone management
- **Card DSL**: Define cards using a human-readable grammar that maps to engine mechanics
- **LLM-Powered Rules Translation**: Natural language rules text is translated to engine instructions via Claude API (with regex fallback)
- **Game Simulation**: Run games between decks to test card interactions
- **CLI**: Command-line interface for running simulations and testing cards
- **Web UI**: Browser-based card designer and game simulator

### Implemented Mechanics

- **All 15 evergreen keywords**: flying, reach, first strike, double strike, deathtouch, trample, lifelink, vigilance, haste, hexproof, menace, defender, flash, indestructible, ward, protection
- **Stack & spells**: cast_spell flow with mana payment, target validation (hexproof/shroud/protection/ward enforcement), LIFO resolution
- **Triggered abilities**: ETB triggers with composable source filters, on-cast triggers, auto-stack placement
- **Auras & Equipment**: attachment rules, aura falloff from protection (SBA), hexproof doesn't block non-cast attachment
- **State-based actions**: lethal damage, 0 toughness, 0 life, poison counters, legend rule, counter cancellation (+1/+1 vs -1/-1), planeswalker 0 loyalty, battle 0 defense, token cease-to-exist, aura legality, saga sacrifice
- **Combat**: full combat step with first strike, double strike, menace, trample, deathtouch, lifelink, vigilance, flying, reach, protection, ward
- **Face-down cards**: morph, disguise (with ward), cloak
- **Transform / DFCs**: day/night, disturb, meld
- **Adventure cards**: cast adventure half, exile, cast creature from exile
- **Sagas & Classes**: full saga lifecycle (ETB lore counter, chapter triggers, sacrifice SBA), class level-up
- **Planeswalkers**: loyalty abilities, uniqueness via legend rule
- **Replacement effects**: ETB modifications (enters tapped, enters with counters), die replacement, draw replacement
- **Continuous effects**: anthem effects, keyword granting/removing
- **Kicker**: optional additional cost for enhanced effects
- **Flashback**: cast from graveyard for alternate cost, exiled on resolution
- **X spells**: variable mana costs (e.g., Blaze deals X damage)
- **Hybrid mana**: {W/U} payable with either color
- **Phyrexian mana**: {R/P} payable with mana or 2 life
- **Cycling**: discard from hand, pay cost, draw a card
- **Prowess**: +1/+1 until end of turn whenever you cast a noncreature spell
- **Format support**: Standard, Modern, Legacy, Vintage, Pioneer, Pauper, Commander (color identity, command zone)
- **Tokens, multi-type cards, Kindred type, sideboard support**

See [docs/GAP_ANALYSIS.md](docs/GAP_ANALYSIS.md) for the full roadmap and remaining work.

## Project Structure

```
mtg_engine/
  core/       # Game state, zones, phases, stack, and rules processing
  dsl/        # Card definition DSL parser and compiler
  cli/        # Command-line interface
  web/        # Flask web application
tests/        # Test suite
cards/        # Card definition files (.mtg)
docs/         # Gap analysis and implementation roadmap
```

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run CLI
python -m mtg_engine.cli

# Run web UI
python -m mtg_engine.web

# Run tests
pytest
```

## Card DSL Example

```
card "Lightning Bolt" {
    type: Instant
    cost: {R}
    effect: damage(target(any_target), 3)
}
```

## License

MIT
