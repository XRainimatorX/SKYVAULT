"""The nine profiles of the military domain pack, as validated models.

Important:
Profiles are the pack's own data, not a SKYVAULT core contract. They are
validated with Pydantic like the core contracts, and load_profiles returns
them with every default filled in, so readers never restate defaults.
"""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PROFILES = REPO_ROOT / "data" / "domains" / "military" / "profiles.json"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UnitProfile(Model):
    role: Literal["combat", "leader", "logistics"]
    hp: int = Field(gt=0)
    move_range: int = Field(ge=0)
    sensor: str
    weapon: str
    ammo: int = Field(ge=0)
    readiness: float = Field(default=1.0, ge=0, le=1)


class FormationProfile(Model):
    slots: list[tuple[int, int]] = Field(min_length=1)


class TerrainProfile(Model):
    symbol: str = Field(min_length=1, max_length=1)
    move_cost: int | None = Field(ge=1)
    cover: float = Field(ge=0, le=1)
    concealment: float = Field(ge=0, le=1)


class SensorProfile(Model):
    range: int = Field(gt=0)


class WeaponProfile(Model):
    range: int = Field(gt=0)
    damage: int = Field(ge=0)
    accuracy: float = Field(ge=0, le=1)
    suppression: int = Field(ge=0)
    ammo_per_shot: int = Field(default=1, ge=0)


class LogisticsProfile(Model):
    ammo_stock: int = Field(ge=0)
    resupply_amount: int = Field(gt=0)
    supply_range: int = Field(default=1, ge=0)
    low_ammo_share: float = Field(default=0.5, ge=0, le=1)


class MoraleProfile(Model):
    start: int = Field(default=80, ge=0, le=100)
    suppress_threshold: int = Field(default=60, ge=0)
    panic_threshold: int = Field(default=85, ge=0)
    retreat_threshold: int = Field(default=25, ge=0)
    suppression_decay: int = Field(default=20, ge=0)
    morale_loss_when_hit: int = Field(default=10, ge=0)
    morale_loss_when_suppressed: int = Field(default=5, ge=0)
    rally: int = Field(default=5, ge=0)

    @model_validator(mode="after")
    def _thresholds_in_order(self) -> "MoraleProfile":
        if self.suppress_threshold > self.panic_threshold:
            raise ValueError("suppress_threshold must not exceed panic_threshold")
        return self


class CommandDelayProfile(Model):
    delay_ticks: int = Field(ge=0, le=3)
    loss_prob: float = Field(ge=0, le=0.2)


class Described(Model):
    description: str


class MilitaryProfiles(Model):
    """Every profile of the pack; names cross-reference each other."""

    pack_id: str
    version: str
    description: str = ""
    units: dict[str, UnitProfile] = Field(min_length=1)
    formations: dict[str, FormationProfile] = Field(min_length=1)
    terrain: dict[str, TerrainProfile] = Field(min_length=1)
    sensors: dict[str, SensorProfile] = Field(min_length=1)
    weapons: dict[str, WeaponProfile] = Field(min_length=1)
    logistics: LogisticsProfile
    morale: MoraleProfile = Field(default_factory=MoraleProfile)
    command_delay: dict[str, CommandDelayProfile] = Field(min_length=1)
    missions: dict[Literal["destroy", "seize", "hold", "delay"], Described]
    doctrines: dict[Literal["aggressive", "overwatch", "defensive"], Described]

    @model_validator(mode="after")
    def _names_resolve(self) -> "MilitaryProfiles":
        for name, unit in self.units.items():
            if unit.sensor not in self.sensors:
                raise ValueError(f"unit {name!r}: unknown sensor {unit.sensor!r}")
            if unit.weapon not in self.weapons:
                raise ValueError(f"unit {name!r}: unknown weapon {unit.weapon!r}")
        symbols = [terrain.symbol for terrain in self.terrain.values()]
        if len(set(symbols)) != len(symbols):
            raise ValueError("terrain symbols must be unique")
        return self


class ProfileError(ValueError):
    """The profiles do not validate; message lists every problem."""


def validate_profiles(data: dict[str, Any]) -> dict[str, Any]:
    """The profiles with every default filled in. Raises ProfileError."""
    try:
        model = MilitaryProfiles.model_validate(data)
    except ValidationError as error:
        problems = [
            ".".join(str(part) for part in item["loc"]) + ": " + item["msg"]
            for item in error.errors()
        ]
        raise ProfileError("; ".join(problems)) from None
    return model.model_dump(mode="json")


def load_profiles(path: Path | None = None) -> dict[str, Any]:
    """The pack's profiles from path (default: data/domains/military)."""
    with Path(path or DEFAULT_PROFILES).open(encoding="utf-8") as file:
        return validate_profiles(json.load(file))
