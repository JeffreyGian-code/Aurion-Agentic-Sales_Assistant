from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.SearchRequest import SearchRequest
from app.models.vehicle import Vehicle


Topic = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,59}$")]


class RecommendationPriority(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    topic: Topic
    required: bool = False


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    priorities: list[RecommendationPriority] = Field(min_length=1, max_length=8)
    filters: SearchRequest | None = None

    @model_validator(mode="after")
    def unique_topics(self):
        if len({priority.topic for priority in self.priorities}) != len(self.priorities):
            raise ValueError("Each recommendation topic must appear only once.")
        return self


class VehicleEvidence(BaseModel):
    topic: Topic
    strength: Literal["confirmed", "indicative"]
    reason: str = Field(min_length=1)
    source: str = Field(min_length=1)


class RecommendedVehicle(BaseModel):
    vehicle: Vehicle
    evidence: list[VehicleEvidence]
    match: Literal["confirmed_match", "candidate", "budget_match", "filter_match"]
