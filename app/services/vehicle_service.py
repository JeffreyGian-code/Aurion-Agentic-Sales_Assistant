from app.models.SearchRequest import SearchRequest, SortOrder
from pydantic import Field, TypeAdapter
from typing import Annotated

from app.models.vehicle import Vehicle
from app.repositories.vehicle_repository import VehicleRepository


VehicleId = Annotated[int, Field(strict=True, gt=0, le=2147483647)]
vehicle_id_adapter = TypeAdapter(VehicleId)


class VehicleService:

    def __init__(self, repository: VehicleRepository):
        self.repository = repository

    def search(
        self,
        brand: str | None = None,
        max_price: int | None = None,
        vehicle_type: str | None = None,
        model: str | None = None,
        variant: str | None = None,
        min_price: int | None = None,
        sort_order: SortOrder = "price_asc",
    ) -> list[Vehicle]:

        criteria = SearchRequest(
            brand=brand,
            max_price=max_price,
            vehicle_type=vehicle_type,
            model=model,
            variant=variant,
            min_price=min_price,
            sort_order=sort_order,
        )

        return self.repository.search(**criteria.model_dump())

    def get_by_id(
        self,
        vehicle_id: int,
    ) -> Vehicle | None:

        return self.repository.get_by_id(vehicle_id_adapter.validate_python(vehicle_id))
