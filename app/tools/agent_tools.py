from functools import cached_property

from langchain_core.tools import StructuredTool, ToolException
from sqlalchemy.exc import SQLAlchemyError

from app.models.emi import EMIRequest
from app.models.recommendation import RecommendationRequest
from app.models.SearchRequest import SearchRequest
from app.models.vehicle import Vehicle
from app.repositories.chroma_vehicle_knowledge import ChromaKnowledgeError, ChromaVehicleKnowledge
from app.repositories.postgres_vehicle_repository import (
    PostgresVehicleRepository,
)
from app.repositories.vehicle_knowledge import VehicleKnowledge
from app.services.finance_service import FinanceService
from app.services.recommendation_service import RecommendationService
from app.services.vehicle_service import VehicleService, VehicleId


class AgentTools:

    def __init__(self):
        repository = PostgresVehicleRepository()

        self.vehicle_service = VehicleService(
            repository=repository
        )
        self.finance_service = FinanceService()

    @cached_property
    def recommendation_service(self) -> RecommendationService:
        try:
            entries = VehicleKnowledge().all_entries()
        except (OSError, ValueError) as exc:
            raise ChromaKnowledgeError("Could not load Markdown evidence.") from exc
        knowledge = ChromaVehicleKnowledge(entries)
        return RecommendationService(self.vehicle_service.repository, knowledge)

    def search_vehicles(
        self,
        request: SearchRequest,
    ) -> list[Vehicle]:
        """Search vehicles using the provided search criteria."""

        try:
            return self.vehicle_service.search(
                brand=request.brand,
                model=request.model,
                variant=request.variant,
                max_price=request.max_price,
                vehicle_type=request.vehicle_type,
                min_price=request.min_price,
                sort_order=request.sort_order,
            )
        except SQLAlchemyError as exc:
            raise ToolException("Inventory is temporarily unavailable.") from exc

    def recommend_vehicles(self, request: RecommendationRequest) -> dict:
        """Recommend exact catalogue variants using local evidence and optional inventory filters."""
        try:
            recommendations = self.recommendation_service.recommend(request)
        except ChromaKnowledgeError as exc:
            raise ToolException("Vehicle recommendation evidence is temporarily unavailable.") from exc
        except SQLAlchemyError as exc:
            raise ToolException("Inventory is temporarily unavailable.") from exc
        return {"recommendations": [item.model_dump(mode="json") for item in recommendations]}

    def get_vehicle_details(
        self,
        vehicle_id: VehicleId,
    ):
        """Get detailed information about a vehicle using its ID."""

        try:
            vehicle = self.vehicle_service.get_by_id(vehicle_id)
        except SQLAlchemyError as exc:
            raise ToolException("Inventory is temporarily unavailable.") from exc

        if vehicle is None:
            return "Vehicle not found."

        return vehicle

    def calculate_emi(
        self,
        principal: float,
        annual_rate: float,
        months: int,
    ) -> dict[str, float]:
        """Calculate monthly EMI and total loan cost."""

        return self.finance_service.calculate_emi(
            principal=principal,
            annual_rate=annual_rate,
            months=months,
        ).model_dump()

    def get_tools(self):
        return [
            StructuredTool.from_function(
                handle_tool_error=True,
                func=self.search_vehicles,
                name="search_vehicles",
                description=(
                    "Search vehicles using brand, model, variant, "
                    "minimum/maximum price, and vehicle type. Returns an ordered "
                    "shortlist of up to three distinct models, or up to three "
                    "variants when model is specified. sort_order defaults to "
                    "price_asc; use price_desc only when requested."
                ),
            ),
            StructuredTool.from_function(
                handle_tool_error=True,
                func=self.recommend_vehicles,
                name="recommend_vehicles",
                handle_validation_error="Invalid recommendation criteria. Check topics and filters.",
                description=(
                    "Use for qualitative criteria such as commuting, parking or automatic. "
                    "Pass priorities in buyer order and mark only firm requirements as required. "
                    "Include SearchRequest filters for any active catalogue constraints. Returns "
                    "up to three ranked variants with exact listed prices and sourced evidence."
                ),
            ),
            StructuredTool.from_function(
                handle_tool_error=True,
                func=self.get_vehicle_details,
                name="get_vehicle_details",
                description=(
                    "Get detailed information about "
                    "a vehicle using its ID."
                ),
            ),
            StructuredTool.from_function(
                handle_tool_error=True,
                func=self.calculate_emi,
                name="calculate_emi",
                args_schema=EMIRequest,
                handle_validation_error=lambda exc: f"Invalid EMI request: {exc}",
                description=(
                    "Calculate monthly EMI and total "
                    "loan cost."
                ),
            ),
        ]
