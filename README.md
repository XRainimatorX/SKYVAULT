# SKYVAULT Day 14 Prototype

SKYVAULT Day 14 Prototype is a Python-based tactical combat simulation prototype.

This project was built as part of a 14-day programming learning process.  
It focuses on object-oriented programming, basic combat simulation, unit roles, target selection, battlefield positioning, movement, weapon range, accuracy, and structured battle recording.

At this stage, the project is a single-file prototype designed for learning and system experimentation.

---

## Current Status

This prototype currently includes:

- Unit system
- Body / state system
- Weapon system
- Team-based combat
- Role-based unit behavior
- Threat score target selection
- BattleMap position system
- Movement system
- Range and accuracy checks
- Attack / miss / damage resolution
- Destroyed unit cleanup
- BattleRecorder logging structure

---

## Core Concepts

The current simulation is built around several main classes:

### `humanbody`

Represents the physical state of a unit.

It stores:

- HP
- AP
- Hunger

It also determines whether a unit is:

- `active`
- `unstable`
- `destroyed`

---

### `groundweapon`

Represents a weapon used by a ground unit.

It stores:

- Weapon name
- Damage
- Attack range
- Accuracy

---

### `groundunit`

Represents a battlefield unit.

It stores:

- Name
- Body
- Weapon
- Skill
- Role
- Team

Current roles include:

- `ASSAULT`
- `COMMAND`
- `SUPPORT`

---

### `UnitManager`

Controls the main combat flow.

It handles:

- Turn and tick flow
- Target selection
- Threat score calculation
- Range checking
- Attack resolution
- Miss handling
- Destroyed unit cleanup
- Battle summary output

---

### `BattleMap`

Controls battlefield space.

It handles:

- Map size
- Unit positions
- Position placement
- Distance calculation
- Range distance calculation
- Movement
- Occupied position checks

Units do not directly store their own `x, y` position.  
Instead, positions are managed by `BattleMap`.

---

### `BattleEngine`

Connects the battlefield components together.

It handles:

- Team setup
- Initial unit placement
- Starting the battle simulation

---

### `BattleRecorder`

Records the battle process in a structured format.

The current logging structure is:

```text
Turn
  Tick
    Unit Action
      Events
```

Current recorded event types include:

- `TARGET_SELECT`
- `MOVE`
- `ATTACK`
- `MISS`
- `DESTROYED`

---

## How the Simulation Works

The simulation follows this general process:

1. Create weapons.
2. Create unit templates.
3. Generate RED and BLUE teams.
4. Place units on the `BattleMap`.
5. Start the battle through `BattleEngine`.
6. Each turn contains several ticks.
7. Each unit acts during each tick.
8. If an enemy is in range, the unit attacks.
9. If no enemy is in range, the unit moves toward a selected target.
10. Attacks are resolved using weapon accuracy.
11. Destroyed units are removed from the battlefield.
12. Battle events are recorded by `BattleRecorder`.

---

## Target Selection

Target selection is based on a weighted threat score model.

The current model considers:

- Enemy HP / vulnerability
- Enemy AP
- Enemy weapon damage
- Enemy role value

Different attacker roles use different weight values.

For example:

- `ASSAULT` uses a balanced scoring model.
- `COMMAND` values important enemy roles more heavily.
- `SUPPORT` values enemy damage more heavily.

If multiple enemies have the same highest score, one is selected randomly.

---

## Movement Logic

If no enemy is currently within weapon range, the unit will attempt to move toward the highest-priority target.

Movement currently works by:

1. Checking nearby candidate positions.
2. Removing positions outside the map.
3. Removing occupied positions.
4. Keeping only positions that reduce distance to the target.
5. Selecting the best position.
6. Moving the unit there.

This is a simple greedy movement system, not full pathfinding.

---

## Range and Accuracy

Weapons have both range and accuracy.

A unit can only attack if the target is within weapon range.

If the target is in range, the attack is resolved using weapon accuracy:

```text
random roll <= weapon accuracy → hit
random roll > weapon accuracy  → miss
```

If the attack hits, damage is applied to the target HP.

---

## Battle Recording

The `BattleRecorder` stores structured battle data.

Example structure:

```text
Turn 1
  Tick 1
    RED Rifleman
      TARGET_SELECT
      MOVE
    RED Heavy_gunner
      TARGET_SELECT
      ATTACK
```

This is not yet a database system.  
It is an in-memory battle recording structure designed for future analysis, debugging, replay, or database integration.

---

## How to Run

Make sure Python is installed.

Then run:

```bash
python main.py
```

---

## Current Limitations

This is still a learning prototype.

Current limitations include:

- Single-file structure
- No external data files
- No database
- No JSON output
- No advanced pathfinding
- No terrain system
- No line-of-sight system
- No armor or penetration system
- No ammunition system
- No advanced command system
- No graphical interface

---

## Project Stage

This project represents the end of the Day 1–14 learning stage.

It is currently focused on building a working tactical simulation core before later restructuring into a cleaner multi-file architecture.

---

## Notes

This repository is a prototype and learning record.

The purpose is not to provide a finished game or complete military simulation, but to build the foundation of a tactical simulation system step by step.