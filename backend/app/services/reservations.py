from datetime import datetime
from decimal import Decimal
from typing import Dict, Any
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "UTC"
DEFAULT_CURRENCY = "USD"


async def _get_property_timezone(session, property_id: str, tenant_id: str) -> str:
    """
    Returns the timezone the property reports its calendar in.
    """
    from sqlalchemy import text

    result = await session.execute(
        text("""
            SELECT timezone
            FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
        """),
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    row = result.fetchone()
    return (row.timezone if row and row.timezone else DEFAULT_TIMEZONE)


def _month_bounds(month: int, year: int, timezone: str) -> tuple:
    """
    Builds the [start, end) bounds of a calendar month in the property's local timezone.
    """
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo(DEFAULT_TIMEZONE)

    start_date = datetime(year, month, 1, tzinfo=tz)
    if month < 12:
        end_date = datetime(year, month + 1, 1, tzinfo=tz)
    else:
        end_date = datetime(year + 1, 1, 1, tzinfo=tz)

    return start_date, end_date


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
) -> Decimal:
    """
    Calculates revenue for a specific month, in the property's local calendar.
    """
    from sqlalchemy import text
    from app.core.database_pool import db_pool

    await db_pool.initialize()

    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    async with db_pool.get_session() as session:
        timezone = await _get_property_timezone(session, property_id, tenant_id)
        start_date, end_date = _month_bounds(month, year, timezone)

        query = text("""
            SELECT COALESCE(SUM(total_amount), 0) as total
            FROM reservations
            WHERE property_id = :property_id
            AND tenant_id = :tenant_id
            AND check_in_date >= :start_date
            AND check_in_date < :end_date
        """)

        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date,
        })
        row = result.fetchone()

    return Decimal(str(row.total)) if row else Decimal("0")


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    # Import database pool
    from app.core.database_pool import db_pool

    # Initialize pool if needed
    await db_pool.initialize()

    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    async with db_pool.get_session() as session:
        # Use SQLAlchemy text for raw SQL
        from sqlalchemy import text

        query = text("""
            SELECT
                currency,
                SUM(total_amount) as total_revenue,
                COUNT(*) as reservation_count
            FROM reservations
            WHERE property_id = :property_id AND tenant_id = :tenant_id
            GROUP BY currency
        """)

        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id
        })
        rows = result.fetchall()

    if not rows:
        # No reservations found for this property
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "0.00",
            "currency": DEFAULT_CURRENCY,
            "count": 0
        }

    if len(rows) > 1:
        currencies = sorted(r.currency for r in rows)
        raise ValueError(
            f"Property {property_id} has reservations in multiple currencies "
            f"({', '.join(currencies)}); cannot produce a single total"
        )

    row = rows[0]
    total_revenue = Decimal(str(row.total_revenue))
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(total_revenue),
        "currency": row.currency or DEFAULT_CURRENCY,
        "count": row.reservation_count
    }
