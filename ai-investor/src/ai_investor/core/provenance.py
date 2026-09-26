"""Provenance des données : chaque valeur sait d'où elle vient et de quand elle date.

Une valeur absente est représentée par `value=None` + `missing_reason`, jamais par 0
ou par une estimation silencieuse.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Generic, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from ai_investor.core.enums import DataReliability

T = TypeVar("T")


class Source(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    reliability: DataReliability
    reference: str | None = None  # URL, nom de fichier importé, identifiant de série…


class DataPoint(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True)

    value: T | None
    source: Source
    as_of: AwareDatetime | None = None  # date de la donnée elle-même
    fetched_at: AwareDatetime  # date d'obtention par l'application
    missing_reason: str | None = None

    @model_validator(mode="after")
    def _missing_is_explicit(self) -> DataPoint[T]:
        if self.value is None and not self.missing_reason:
            raise ValueError("Valeur manquante : missing_reason est obligatoire.")
        if self.value is not None and self.missing_reason:
            raise ValueError("missing_reason n'a de sens que si la valeur est absente.")
        if self.as_of is not None and self.as_of > self.fetched_at + timedelta(minutes=5):
            raise ValueError("Donnée datée dans le futur par rapport à sa date d'obtention.")
        return self

    @property
    def is_missing(self) -> bool:
        return self.value is None

    def is_stale(self, now: datetime, max_age: timedelta) -> bool:
        """Une donnée sans date est considérée comme périmée (fraîcheur non prouvable)."""
        if self.as_of is None:
            return True
        return now - self.as_of > max_age
