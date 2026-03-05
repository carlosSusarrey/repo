# MTG Rules Engine

A Magic: The Gathering rules engine for designing and testing custom cards. Define cards using a domain-specific language (DSL), simulate games, and see how mechanics interact.

## Features

- **Rules Engine**: Implements MTG game rules including phases, priority, the stack, and zone management
- **Card DSL**: Define cards using a human-readable grammar that maps to engine mechanics
- **Game Simulation**: Run games between decks to test card interactions
- **CLI**: Command-line interface for running simulations and testing cards
- **Web UI**: Browser-based card designer and game simulator

## Project Structure

```
mtg_engine/
  core/       # Game state, zones, phases, stack, and rules processing
  dsl/        # Card definition DSL parser and compiler
  cli/        # Command-line interface
  web/        # Flask web application
tests/        # Test suite
cards/        # Card definition files (.mtg)
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
