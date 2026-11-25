from abc import ABC, abstractmethod

from app.models.SearchRequest import SearchRequest, SortOrder
from app.models.vehicle import Vehicle


class VehicleRepository(ABC):

    @abstractmethod
    def search(
        self,
        brand: str | None = None,
        model: str | None = None,
        variant: str | None = None,
        max_price: int | None = None,
        vehicle_type: str | None = None,
        min_price: int | None = None,
        sort_order: SortOrder = "price_asc",
    ) -> list[Vehicle]:
        pass

    @abstractmethod
    def get_by_id(
        self,
        vehicle_id: int,
    ) -> Vehicle | None:
        pass

    @abstractmethod
    def get_by_ids(self, vehicle_ids: list[int]) -> list[Vehicle]:
        pass

    @abstractmethod
    def search_candidates(self, request: SearchRequest) -> list[Vehicle]:
        pass
