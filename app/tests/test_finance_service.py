import math

import pytest
from pydantic import ValidationError

from app.models.emi import EMIRequest, EMIResult
from app.services.finance_service import EMIValidationError, FinanceService
from app.tools.agent_tools import AgentTools


def test_calculate_emi():

    service = FinanceService()

    result = service.calculate_emi(
        principal=800000,
        annual_rate=8.5,
        months=60,
    )

    assert isinstance(result, EMIResult)
    assert result.monthly_emi == pytest.approx(16413.23)
    assert result.total_payment == pytest.approx(984793.50)
    assert result.total_interest == pytest.approx(184793.50)

def test_calculate_emi_zero_interest():

    service = FinanceService()

    result = service.calculate_emi(
        principal=120000,
        annual_rate=0,
        months=12,
    )

    assert result.monthly_emi == pytest.approx(10000)
    assert result.total_interest == pytest.approx(0)


INVALID_INPUTS = [
    (field, value)
    for field, values in {
        "principal": [0, -1, 0.001, 1_000_000_001, float("nan"),
                      float("inf"), -float("inf"), True, "800000", None],
        "annual_rate": [-1, 100.01, 1e308, float("nan"), float("inf"),
                        -float("inf"), False, "8.5", None],
        "months": [0, -1, 601, 10**9, 1.5, 60.0, float("nan"),
                   float("inf"), -float("inf"), True, "60", None],
    }.items()
    for value in values
]


@pytest.fixture
def emi_tool():
    return next(tool for tool in AgentTools().get_tools() if tool.name == "calculate_emi")


@pytest.mark.parametrize(("field", "value"), INVALID_INPUTS)
def test_invalid_inputs_at_all_boundaries(field, value, emi_tool):
    inputs = {"principal": 800000, "annual_rate": 8.5, "months": 60}
    inputs[field] = value
    with pytest.raises(ValidationError):
        EMIRequest(**inputs)
    with pytest.raises(EMIValidationError, match=field):
        FinanceService().calculate_emi(**inputs)
    # Direct wrapper calls bypass the StructuredTool schema.
    with pytest.raises(EMIValidationError, match=field):
        AgentTools().calculate_emi(**inputs)
    error = emi_tool.invoke(inputs)
    assert error.startswith("Invalid EMI request:")
    assert field in error


def test_extreme_rate_and_duration_are_validation_errors():
    with pytest.raises(EMIValidationError):
        FinanceService().calculate_emi(800000, 1e308, 10**9)


@pytest.mark.parametrize(("principal", "annual_rate", "months"), [
    (0.01, 0, 1),
    (0.01, 100, 600),
    (1_000_000_000, 100, 600),
    (100, 5e-324, 600),
])
def test_supported_boundaries(principal, annual_rate, months):
    result = FinanceService().calculate_emi(principal, annual_rate, months)
    assert isinstance(result, EMIResult)
    assert result.total_payment >= principal
    assert result.total_interest >= 0
    assert all(math.isfinite(v) for v in result.model_dump().values())


def test_half_up_rounding_and_unrounded_totals():
    result = FinanceService().calculate_emi(0.01, 0, 2)
    assert result.monthly_emi == 0.01  # Exact half-paise rounds up.
    assert result.total_payment == 0.01
    assert result.total_interest == 0
    result = FinanceService().calculate_emi(1, 0, 3)
    assert result.monthly_emi == 0.33
    assert result.total_payment == 1  # Not 0.33 * 3.
    assert result.total_interest == 0


def test_tool_uses_shared_schema_and_serializes_result(emi_tool):
    assert emi_tool.args_schema is EMIRequest
    result = emi_tool.invoke({"principal": 800000, "annual_rate": 8.5, "months": 60})
    assert result == {"monthly_emi": 16413.23, "total_payment": 984793.50,
                      "total_interest": 184793.50}


def test_tool_rejects_missing_and_extra_fields(emi_tool):
    assert "Invalid EMI request" in emi_tool.invoke({"principal": 1})
    assert "Invalid EMI request" in emi_tool.invoke({
        "principal": 1, "annual_rate": 0, "months": 1, "unexpected": 1,
    })
