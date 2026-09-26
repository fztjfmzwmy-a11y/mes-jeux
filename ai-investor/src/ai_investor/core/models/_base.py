from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Base : immuable, champs inconnus refusés, NaN/infini refusés."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
