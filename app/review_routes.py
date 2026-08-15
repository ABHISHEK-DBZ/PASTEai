from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.events import publish
from app.models import (
    FieldAudit,
    FieldType,
    Product,
    ProductField,
    ProductStatus,
    ReviewStatus,
)

router = APIRouter(prefix="/api/v1/review", tags=["review"])

# A pending field "needs review" exactly when the trust model would NOT
# auto-approve it (see trust_model.determine_routing): PROVED + confidence
# >= 0.90 + extraction strength >= 0.5 + no constraint violation.
# Everything else goes to the HITL queue.
AUTO_APPROVE_OK = and_(
    ProductField.field_type == FieldType.PROVED,
    ProductField.confidence >= 0.9,
    or_(ProductField.extraction_strength.is_(None), ProductField.extraction_strength >= 0.5),
    ProductField.constraint_violation == False,  # noqa: E712
)
NEEDS_REVIEW = ~AUTO_APPROVE_OK

SEVERITY_PREDICATES: dict[str, list] = {
    "dispute": [ProductField.field_type == FieldType.DISPUTE],
    "forced_review": [ProductField.extraction_strength < 0.5],
    "constraint_violation": [ProductField.constraint_violation == True],  # noqa: E712
    "inferred": [ProductField.field_type == FieldType.INFERRED],
    # Every PROVED field below the auto-approve threshold is borderline.
    "borderline": [
        ProductField.field_type == FieldType.PROVED,
        ProductField.confidence < 0.9,
    ],
}


def _base_pending_query():
    """Pending fields that genuinely need human review (union of severities)."""
    return (
        select(ProductField)
        .join(Product)
        .options(selectinload(ProductField.product))
        .where(
            ProductField.review_status == ReviewStatus.PENDING,
            NEEDS_REVIEW,
        )
    )


def _issue_for(f: ProductField) -> str:
    if f.field_type == FieldType.DISPUTE:
        return "dispute"
    if f.extraction_strength is not None and f.extraction_strength < 0.5:
        return "forced_review"
    if f.constraint_violation:
        return "constraint_violation"
    if f.field_type == FieldType.INFERRED:
        return "inferred"
    return "borderline"


async def _recompute_product_status(session: AsyncSession, product: Product) -> None:
    """After a review action, update the product status once no fields remain pending.

    The product only becomes EXPORTED if at least one field was accepted/edited;
    a product whose fields were all rejected stays in REVIEW (nothing to publish).
    """
    remaining = await session.scalar(
        select(func.count(ProductField.id)).where(
            ProductField.product_id == product.id,
            ProductField.review_status == ReviewStatus.PENDING,
        )
    )
    if remaining:
        return
    accepted = await session.scalar(
        select(func.count(ProductField.id)).where(
            ProductField.product_id == product.id,
            ProductField.review_status.in_([ReviewStatus.ACCEPTED, ReviewStatus.EDITED]),
        )
    )
    if accepted:
        product.status = ProductStatus.EXPORTED
        product.completed_at = datetime.now(timezone.utc)
    else:
        product.status = ProductStatus.REVIEW
        product.completed_at = None
    await session.flush()
    await session.commit()
    publish(
        "product:status",
        {
            "product_id": str(product.id),
            "status": product.status.value,
            "part_number": product.part_number,
            "source_filename": product.source_filename,
        },
    )


def _record_audit(
    session: AsyncSession,
    field: ProductField,
    action: str,
    old_value: dict | None,
    new_value: dict | None,
) -> None:
    session.add(
        FieldAudit(
            field_id=field.id,
            action=action,
            old_value=old_value,
            new_value=new_value,
            actor="user",
        )
    )


@router.get("/queue")
async def get_review_queue(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    severity: str | None = Query(None),
    category: str | None = Query(None),
    product_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    stmt = _base_pending_query()

    if severity and severity in SEVERITY_PREDICATES:
        stmt = stmt.where(*SEVERITY_PREDICATES[severity])
    if category:
        stmt = stmt.where(Product.category == category)
    if product_id:
        stmt = stmt.where(ProductField.product_id == product_id)

    # Count total (filtered)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    # Per-severity stats, honoring category/product filters
    stats: dict[str, int] = {}
    for sev, preds in SEVERITY_PREDICATES.items():
        sev_stmt = _base_pending_query().where(*preds)
        if category:
            sev_stmt = sev_stmt.where(Product.category == category)
        if product_id:
            sev_stmt = sev_stmt.where(ProductField.product_id == product_id)
        sev_count = select(func.count()).select_from(sev_stmt.subquery())
        stats[sev] = (await session.execute(sev_count)).scalar() or 0

    # Paginate
    stmt = stmt.order_by(ProductField.created_at.desc()).offset((page - 1) * size).limit(size)
    fields = (await session.execute(stmt)).scalars().all()

    items = []
    for f in fields:
        items.append(
            {
                "field_id": str(f.id),
                "product_id": str(f.product_id),
                "product_part_number": f.product.part_number,
                "attribute_key": f.attribute_key,
                "attribute_label": f.attribute_label,
                "value": f.value,
                "unit": f.unit,
                "field_type": f.field_type.value,
                "confidence": f.confidence,
                "extraction_strength": f.extraction_strength,
                "routing_issue": _issue_for(f),
                "sources": f.sources,
                "reason_chain": f.reason_chain,
            }
        )

    pages = (total + size - 1) // size

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
        "stats": stats,
    }


@router.get("/fields/{field_id}")
async def get_field_detail(field_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(ProductField).where(ProductField.id == field_id)
    field = (await session.execute(stmt)).scalar_one_or_none()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    stmt_p = (
        select(Product)
        .where(Product.id == field.product_id)
        .options(selectinload(Product.fields))
    )
    product = (await session.execute(stmt_p)).scalar_one_or_none()

    return {
        "field": {
            "id": str(field.id),
            "attribute_key": field.attribute_key,
            "attribute_label": field.attribute_label,
            "value": field.value,
            "unit": field.unit,
            "field_type": field.field_type.value,
            "confidence": field.confidence,
            "extraction_strength": field.extraction_strength,
            "source_authority": field.source_authority,
            "agreement": field.agreement,
            "sources": field.sources,
            "reason_chain": field.reason_chain,
            "physical_constraints": field.physical_constraints,
            "constraint_violation": field.constraint_violation,
            "review_status": field.review_status.value,
        },
        "product": {
            "id": str(product.id),
            "part_number": product.part_number,
            "manufacturer": product.manufacturer,
            "category": product.category,
            "source_filename": product.source_filename,
            "fields": [
                {
                    "id": str(f.id),
                    "attribute_key": f.attribute_key,
                    "attribute_label": f.attribute_label,
                    "value": f.value,
                    "unit": f.unit,
                    "field_type": f.field_type.value,
                    "confidence": f.confidence,
                    "sources": f.sources,
                    "reason_chain": f.reason_chain,
                    "review_status": f.review_status.value,
                }
                for f in product.fields
            ],
        },
        # Evidence scoped to the field under review
        "sources": [
            {
                "ref": s.get("ref", ""),
                "authority": s.get("authority", 0),
                "agreement": s.get("agreement", ""),
                "evidence_text": s.get("evidence_text", ""),
            }
            for s in field.sources
        ],
    }


class FieldReviewUpdate(BaseModel):
    value: str | None = None
    unit: str | None = None
    review_status: ReviewStatus = ReviewStatus.ACCEPTED


@router.patch("/fields/{field_id}")
async def update_field_review(
    field_id: uuid.UUID,
    update: FieldReviewUpdate,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(ProductField).where(ProductField.id == field_id)
    field = (await session.execute(stmt)).scalar_one_or_none()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    old_value = {"value": field.value, "unit": field.unit, "review_status": field.review_status.value}
    if update.value is not None:
        field.value = update.value
    if update.unit is not None:
        field.unit = update.unit
    field.review_status = update.review_status
    field.reviewed_by = "user"  # In real app: get from auth
    field.reviewed_at = datetime.now(timezone.utc)

    _record_audit(
        session,
        field,
        action="reviewed",
        old_value=old_value,
        new_value={
            "value": field.value,
            "unit": field.unit,
            "review_status": field.review_status.value,
        },
    )

    product = await session.get(Product, field.product_id)
    await session.commit()

    publish(
        "field:reviewed",
        {
            "field_id": str(field_id),
            "product_id": str(field.product_id),
            "review_status": update.review_status.value,
        },
    )
    if product is not None:
        await _recompute_product_status(session, product)

    return {"status": "ok", "field_id": str(field_id), "review_status": update.review_status.value}


@router.post("/products/{product_id}/accept-all")
async def accept_all_fields(product_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await _bulk_review(product_id, ReviewStatus.ACCEPTED, session)


@router.post("/products/{product_id}/reject-all")
async def reject_all_fields(product_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await _bulk_review(product_id, ReviewStatus.REJECTED, session)


async def _bulk_review(product_id: uuid.UUID, review_status: ReviewStatus, session: AsyncSession) -> dict:
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    stmt = select(ProductField).where(
        ProductField.product_id == product_id,
        ProductField.review_status == ReviewStatus.PENDING,
    )
    fields = (await session.execute(stmt)).scalars().all()
    now = datetime.now(timezone.utc)
    for f in fields:
        old_value = {"value": f.value, "unit": f.unit, "review_status": f.review_status.value}
        f.review_status = review_status
        f.reviewed_by = "user"
        f.reviewed_at = now
        _record_audit(
            session,
            f,
            action="reviewed",
            old_value=old_value,
            new_value={"value": f.value, "unit": f.unit, "review_status": f.review_status.value},
        )

    await session.commit()
    publish(
        "field:reviewed",
        {
            "product_id": str(product_id),
            "review_status": review_status.value,
            "count": len(fields),
        },
    )
    await _recompute_product_status(session, product)

    return {"status": "ok", "updated": len(fields), "review_status": review_status.value}


@router.get("/stats")
async def get_review_stats(session: AsyncSession = Depends(get_session)):
    # Overall stats
    stmt = select(ProductField.field_type, func.count(ProductField.id)).where(
        ProductField.review_status == ReviewStatus.PENDING,
    ).group_by(ProductField.field_type)
    by_type = {row[0].value: row[1] for row in (await session.execute(stmt)).all()}

    # Products in review
    products_in_review = (
        await session.scalar(
            select(func.count(Product.id)).where(Product.status == ProductStatus.REVIEW)
        )
        or 0
    )

    return {
        "by_type": by_type,
        "products_in_review": products_in_review,
        "total_pending": sum(by_type.values()),
    }
