from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

CENTS = Decimal("0.01")


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=403,
            detail="No tenant associated with this account",
        )

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    try:
        exact_total = Decimal(str(revenue_data['total']))
    except (InvalidOperation, TypeError):
        raise HTTPException(status_code=500, detail="Malformed revenue total")

    rounded_total = exact_total.quantize(CENTS, rounding=ROUND_HALF_UP)

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": str(rounded_total),
        "total_revenue_exact": str(exact_total),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
