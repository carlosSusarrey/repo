# MTG Rules Engine

A Magic: The Gathering rules engine for designing and testing custom cards. Define cards using a domain-specific language (DSL), simulate games, and see how mechanics interact.

## Features

- **Rules Engine**: Implements MTG game rules including phases, priority, the stack, and zone management
- **Card DSL**: Define cards using a human-readable grammar that maps to engine mechanics
- **Game Simulation**: Run games between decks to test card interactions
- **CLI**: Command-line interface for running simulations and testing cards
- **Web UI**: Browser-based card designer and game simulator

### Implemented Mechanics

- **All 15 evergreen keywords**: flying, reach, first strike, double strike, deathtouch, trample, lifelink, vigilance, haste, hexproof, menace, defender, flash, indestructible, ward, protection
- **Stack & spells**: cast_spell flow with mana payment, target validation (hexproof/shroud/protection/ward enforcement), LIFO resolution
- **Triggered abilities**: ETB triggers with composable source filters, on-cast triggers, auto-stack placement
- **Auras & Equipment**: attachment rules, aura falloff from protection (SBA), hexproof doesn't block non-cast attachment
- **Face-down cards**: morph, disguise (with ward), cloak
- **Transform / DFCs**: day/night, disturb, meld
- **Adventure cards**: cast adventure half, exile, cast creature from exile
- **Combat**: declare attackers/blockers, damage assignment, keyword interactions
- **Format support**: Standard, Modern, Legacy, Vintage, Pioneer, Pauper, Commander (color identity, command zone)
- **Tokens, multi-type cards, Kindred type, sideboard support**
- **457 tests** covering all implemented features

See [docs/GAP_ANALYSIS.md](docs/GAP_ANALYSIS.md) for the full roadmap and remaining work.

## Project Structure

```
mtg_engine/
  core/       # Game state, zones, phases, stack, and rules processing
  dsl/        # Card definition DSL parser and compiler
  cli/        # Command-line interface
  web/        # Flask web application
tests/        # Test suite (457 tests)
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
