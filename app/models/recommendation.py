import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.SearchRequest import SearchRequest
from app.models.vehicle import Vehicle


Topic = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,59}$")]


Preference = Annotated[str, Field(min_length=3, max_length=160)]
PERSONAL_DETAIL = re.compile(
    r"[@\r\n]|https?://|www\.|(?:\d[\s().+\-]*){5,}|"
    r"\b(?:my name|i live|my address|phone number|aadhaar|passport number)\b",
    re.IGNORECASE,
)


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)

    preferences: list[Preference] = Field(default_factory=list, max_length=8)
    required_topics: list[Topic] = Field(default_factory=list, max_length=8)
    filters: SearchRequest | None = None

    @field_validator("preferences")
    @classmethod
    def vehicle_phrases(cls, preferences):
        if any(PERSONAL_DETAIL.search(phrase) for phrase in preferences):
            raise ValueError("Use short vehicle preferences without personal details.")
        return preferences

    @model_validator(mode="after")
    def has_criteria(self):
        if not self.preferences and not self.required_topics:
            raise ValueError("Add a preference or a firm requirement.")
        if len(set(self.required_topics)) != len(self.required_topics):
            raise ValueError("Each firm requirement must appear only once.")
        return self


class VehicleEvidence(BaseModel):
    topic: Topic
    strength: Literal["confirmed", "indicative"]
    reason: str = Field(min_length=1)
    source: str = Field(min_length=1)


class RecommendedVehicle(BaseModel):
    vehicle: Vehicle
    evidence: list[VehicleEvidence]
    matched_preferences: list[str]
    match: Literal["confirmed_match", "candidate", "budget_match"]


class RecommendationResult(BaseModel):
    status: Literal["matches", "clarification_needed", "requirements_unverified", "no_catalogue_matches"]
    recommendations: list[RecommendedVehicle] = Field(default_factory=list)
