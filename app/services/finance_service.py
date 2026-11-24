from decimal import ROUND_HALF_UP, Decimal, localcontext

from pydantic import ValidationError

from app.models.emi import EMIRequest, EMIResult


class EMIValidationError(ValueError):
    """The supplied loan inputs violate the EMIRequest contract."""


class FinanceService:

    def calculate_emi(
        self,
        principal: float,
        annual_rate: float,
        months: int,
    ) -> EMIResult:
        """Validate direct callers and estimate fixed-rate repayments.

        Use decimal arithmetic, rounding each output independently to nearest
        paise (two decimals), with ties away from zero (ROUND_HALF_UP).
        Totals use the unrounded EMI to avoid accumulated monthly rounding
        error. No fees or final-payment adjustment are modeled.
        """
        try:
            request = EMIRequest(
                principal=principal, annual_rate=annual_rate, months=months
            )
        except ValidationError as exc:
            raise EMIValidationError(f"Invalid EMI request: {exc}") from exc

        amount = Decimal(str(request.principal))
        rate = Decimal(str(request.annual_rate))
        with localcontext() as context:
            # Preserve 1 + rate even for tiny, positive finite float inputs.
            context.prec = 40 + max(0, -rate.adjusted())
            monthly_rate = rate / 1200
            if not monthly_rate:
                emi = amount / request.months
            else:
                # Negative powers avoid the growth term in the usual formula.
                emi = amount * monthly_rate / (
                    1 - (1 + monthly_rate) ** (-request.months)
                )
            total_payment = max(amount, emi * request.months)
            total_interest = total_payment - amount

            def rounded(value: Decimal) -> float:
                return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

            return EMIResult(
                monthly_emi=rounded(emi),
                total_payment=rounded(total_payment),
                total_interest=rounded(total_interest),
            )
