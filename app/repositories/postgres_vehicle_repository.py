from sqlalchemy import bindparam, text

from app.database import engine
from app.models.SearchRequest import SearchRequest, SortOrder
from app.models.vehicle import Vehicle
from app.repositories.vehicle_repository import VehicleRepository


class PostgresVehicleRepository(VehicleRepository):
    """PostgreSQL implementation of the vehicle repository."""

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
        request = SearchRequest(
            brand=brand, model=model, variant=variant, max_price=max_price,
            vehicle_type=vehicle_type, min_price=min_price, sort_order=sort_order,
        )
        return self._search(request, shortlist=True)

    def search_candidates(self, request: SearchRequest) -> list[Vehicle]:
        return self._search(request, shortlist=False)

    def _search(self, request: SearchRequest, *, shortlist: bool) -> list[Vehicle]:
        # Only allow fixed SQL directions; customer input is never interpolated.
        directions = {"price_asc": "ASC", "price_desc": "DESC"}
        direction = directions[request.sort_order]
        query = """
            SELECT id, model, brand, price, vehicle_type, variant
            FROM vehicles
        """

        conditions: list[str] = []
        parameters: dict[str, str | int] = {}

        for column in ("brand", "model", "variant", "vehicle_type"):
            value = getattr(request, column)
            if value is not None:
                conditions.append(f"LOWER({column}) = LOWER(:{column})")
                parameters[column] = value

        if request.max_price is not None:
            conditions.append("price <= :max_price")
            parameters["max_price"] = request.max_price

        if request.min_price is not None:
            conditions.append("price >= :min_price")
            parameters["min_price"] = request.min_price

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        if shortlist and request.model is None:
            # Filter before choosing one representative per brand/model.
            query = f"""
                SELECT id, model, brand, price, vehicle_type, variant
                FROM (
                    SELECT filtered.*, ROW_NUMBER() OVER (
                        PARTITION BY LOWER(brand), LOWER(model)
                        ORDER BY price {direction}, id ASC
                    ) AS model_rank
                    FROM ({query}) AS filtered
                ) AS ranked
                WHERE model_rank = 1
            """

        query += f" ORDER BY price {direction}, id ASC"
        if shortlist:
            query += " LIMIT 3"
        return self._fetch(text(query), parameters)

    def get_by_id(
        self,
        vehicle_id: int,
    ) -> Vehicle | None:
        vehicles = self.get_by_ids([vehicle_id])
        return vehicles[0] if vehicles else None

    def get_by_ids(self, vehicle_ids: list[int]) -> list[Vehicle]:
        if not vehicle_ids:
            return []
        query = text("""
            SELECT id, model, brand, price, vehicle_type, variant
            FROM vehicles
            WHERE id IN :vehicle_ids
        """).bindparams(bindparam("vehicle_ids", expanding=True))
        return self._fetch(query, {"vehicle_ids": vehicle_ids})

    @staticmethod
    def _fetch(query, parameters) -> list[Vehicle]:
        with engine.connect() as connection:
            rows = connection.execute(query, parameters).mappings().all()
        return [Vehicle.model_validate(row) for row in rows]
