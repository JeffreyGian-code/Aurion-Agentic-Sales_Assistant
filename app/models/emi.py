"""Validated inputs and monetary outputs for the EMI estimate."""

from pydantic import BaseModel, ConfigDict, Field


class EMIRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)

    principal: float = Field(
        ge=0.01, le=1_000_000_000, description="Loan amount in INR (0.01 to 1 billion)."
    )
    annual_rate: float = Field(
        ge=0, le=100, description="Annual interest percentage (0 to 100, inclusive)."
    )
    months: int = Field(
        ge=1, le=600, description="Whole number of monthly payments (1 to 600)."
    )


class EMIResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)

    monthly_emi: float = Field(ge=0)
    total_payment: float = Field(ge=0)
    total_interest: float = Field(ge=0)
