from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SortOrder = Literal["price_asc", "price_desc"]


class SearchRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True, str_min_length=1, str_max_length=120)
    brand: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=120)
    max_price: int | None = Field(default=None, ge=0)
    vehicle_type: str | None = Field(default=None, max_length=40)
    variant: str | None = Field(default=None, max_length=100)
    min_price: int | None = Field(default=None, ge=0)
    sort_order: SortOrder = "price_asc"

    @model_validator(mode="after")
    def validate_price_range(self):
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("min_price cannot exceed max_price")
        return self
