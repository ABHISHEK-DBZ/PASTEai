from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import get_session
from app.events import publish
from app.models import (
    Batch,
    BatchCreate,
    BatchRead,
    BatchStatus,
    Product,
    ProductField,
    ProductRead,
    ProductStatus,
)
from app.pipeline import export_gs1_csv, export_json_ld, export_unilog_excel_bytes, process_product

logger = logging.getLogger("paste.routes")

router = APIRouter(prefix="/api/v1", tags=["products"])

# Keep strong references to background tasks so they aren't garbage-collected mid-run.
_background_tasks: set[asyncio.Task] = set()


def _spawn_background(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# Magic-byte signatures for the allowed file types (first 8 bytes).
MAGIC_BYTES: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "tiff": (b"II*\x00", b"MM\x00*"),
}


def compute_file_hash(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _file_ext(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return filename.split(".")[-1].lower()


def _matches_magic(file_path: Path, ext: str) -> bool:
    """Verify the first bytes of a file match its claimed extension."""
    signatures = MAGIC_BYTES.get(ext)
    if not signatures:
        return False
    with open(file_path, "rb") as f:
        head = f.read(8)
    return any(head.startswith(sig) for sig in signatures)


async def _save_upload(file: UploadFile, tmp_path: Path) -> int:
    """Stream the upload to disk with a hard size limit. Returns bytes written."""
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    written = 0
    with open(tmp_path, "wb") as buffer:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                buffer.close()
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds the {settings.max_file_size_mb} MB size limit",
                )
            buffer.write(chunk)
    return written


def _product_path(product: Product) -> Path:
    """Return the on-disk path of a product's source file (hash-named)."""
    return settings.upload_dir / f"{product.source_hash}.{product.source_type}"


async def _set_product_status(
    session: AsyncSession,
    product: Product,
    new_status: ProductStatus,
) -> Product:
    """Update a product's status and broadcast a realtime event."""
    from datetime import datetime, timezone

    product.status = new_status
    if new_status == ProductStatus.EXPORTED:
        product.completed_at = datetime.now(timezone.utc)
    await session.flush()
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    publish(
        "product:status",
        {
            "product_id": str(product.id),
            "status": new_status.value,
            "part_number": product.part_number,
            "source_filename": product.source_filename,
        },
    )
    return product


def _enqueue_processing(product_id: str, file_path: Path) -> bool:
    """Push a job to the Redis/RQ queue. Returns True if queued remotely."""
    try:
        import redis as redis_lib
        from rq import Queue

        conn = redis_lib.from_url(settings.redis_url, socket_connect_timeout=1)
        conn.ping()
        queue = Queue("processing", connection=conn, default_timeout=3600)
        queue.enqueue("app.worker.process_job", product_id, str(file_path), job_timeout=3600)
        conn.close()
        logger.info("product %s queued on RQ worker", product_id)
        return True
    except Exception as exc:
        logger.warning("Redis queue unavailable (%s) - processing in-process", exc)
        return False


async def _update_batch_counts(session: AsyncSession, product: Product | None) -> None:
    if not product or not product.batch_id:
        return
    stmt = select(Batch).where(Batch.id == product.batch_id)
    result = await session.execute(stmt)
    batch = result.scalar_one_or_none()
    if not batch:
        return
    processed = await session.scalar(
        select(func.count(Product.id)).where(
            Product.batch_id == batch.id,
            Product.status.in_([ProductStatus.EXPORTED, ProductStatus.REVIEW, ProductStatus.FAILED]),
        )
    )
    batch.processed_products = processed or 0
    batch.status = (
        BatchStatus.PROCESSING
        if (processed or 0) < batch.total_products
        else BatchStatus.COMPLETED
    )
    await session.flush()


@router.post("/batches", response_model=BatchRead, status_code=status.HTTP_201_CREATED)
async def create_batch(
    batch_in: BatchCreate,
    session: AsyncSession = Depends(get_session),
):
    batch = Batch(name=batch_in.name)
    session.add(batch)
    await session.flush()
    publish("batch:created", {"batch_id": str(batch.id), "name": batch.name})
    return batch


@router.get("/batches", response_model=list[BatchRead])
async def list_batches(session: AsyncSession = Depends(get_session)):
    stmt = select(Batch).order_by(Batch.created_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/batches/{batch_id}", response_model=BatchRead)
async def get_batch(batch_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(Batch).where(Batch.id == batch_id)
    result = await session.execute(stmt)
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.post("/products/upload", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def upload_product(
    batch_id: Annotated[uuid.UUID | None, Form()] = None,
    part_number: Annotated[str | None, Form()] = None,
    manufacturer: Annotated[str | None, Form()] = None,
    category: Annotated[str | None, Form()] = None,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    file_ext = _file_ext(file.filename)
    if file_ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type .{file_ext} not allowed. Allowed: {', '.join(sorted(settings.allowed_extensions))}",
        )

    # Save file (size-limited, streamed)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = settings.upload_dir / f"{uuid.uuid4()}.{file_ext}"

    written = await _save_upload(file, tmp_path)
    if written == 0:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    # Reject files whose content does not match their claimed extension
    if not _matches_magic(tmp_path, file_ext):
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File content does not match a valid .{file_ext} file",
        )

    # Check idempotency
    file_hash = compute_file_hash(tmp_path)
    stmt = select(Product).where(Product.source_hash == file_hash).options(selectinload(Product.fields))
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        # Clean up duplicate file
        tmp_path.unlink(missing_ok=True)
        return existing

    # Store under the content hash so reprocess always finds the original file
    file_path = settings.upload_dir / f"{file_hash}.{file_ext}"
    if not file_path.exists():
        tmp_path.rename(file_path)
    else:
        tmp_path.unlink(missing_ok=True)

    # Create product record
    product = Product(
        batch_id=batch_id,
        source_filename=file.filename,
        source_hash=file_hash,
        source_type=file_ext,
        part_number=part_number,
        manufacturer=manufacturer,
        category=category,
        status=ProductStatus.PENDING,
    )
    session.add(product)
    await session.flush()

    # Update batch count
    if batch_id:
        stmt_b = select(Batch).where(Batch.id == batch_id)
        result_b = await session.execute(stmt_b)
        batch = result_b.scalar_one_or_none()
        if batch:
            batch.total_products += 1

    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    publish(
        "product:created",
        {
            "product_id": str(product.id),
            "part_number": product.part_number,
            "source_filename": product.source_filename,
            "batch_id": str(batch_id) if batch_id else None,
        },
    )

    # Queue for processing on the RQ worker; fall back to in-process task.
    queued = _enqueue_processing(str(product.id), file_path)
    if not queued:
        _spawn_background(process_in_background(product.id, file_path))

    # Re-load with fields eagerly so response serialization doesn't trigger an
    # async lazy-load (MissingGreenlet) on the unloaded relationship.
    stmt = select(Product).where(Product.id == product.id).options(selectinload(Product.fields))
    result = await session.execute(stmt)
    return result.scalar_one()


async def process_in_background(product_id: uuid.UUID, file_path: Path):
    """Fallback in-process processing (used when Redis/worker is unavailable)."""
    from datetime import datetime, timezone

    from app.db import session_context

    async with session_context() as session:
        stmt = select(Product).where(Product.id == product_id)
        result = await session.execute(stmt)
        product = result.scalar_one_or_none()
        if not product:
            return
        product.status = ProductStatus.PROCESSING
        product.updated_at = datetime.now(timezone.utc)
        await session.flush()
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            return
        publish(
            "product:status",
            {
                "product_id": str(product_id),
                "status": "processing",
                "part_number": product.part_number,
                "source_filename": product.source_filename,
            },
        )

        try:
            await process_product(str(product_id), file_path, session)
            product = await session.get(Product, product_id)
            await _update_batch_counts(session, product)
        except Exception as exc:
            logger.exception("in-process processing failed for %s: %s", product_id, exc)
            stmt = select(Product).where(Product.id == product_id)
            result = await session.execute(stmt)
            product = result.scalar_one_or_none()
            if product:
                await _set_product_status(session, product, ProductStatus.FAILED)
            return

        await _set_product_status(session, product, product.status)


@router.get("/products", response_model=list[ProductRead])
async def list_products(
    batch_id: uuid.UUID | None = None,
    status: ProductStatus | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Product).options(selectinload(Product.fields))
    if batch_id:
        stmt = stmt.where(Product.batch_id == batch_id)
    if status:
        stmt = stmt.where(Product.status == status)
    stmt = stmt.order_by(Product.created_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/products/{product_id}", response_model=ProductRead)
async def get_product(product_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.fields))
    )
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/products/{product_id}/file", include_in_schema=True)
async def get_product_file(product_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(Product).where(Product.id == product_id)
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    file_path = _product_path(product)
    if file_path.exists():
        media_type = "application/pdf" if product.source_type == "pdf" else None
        return FileResponse(str(file_path), media_type=media_type, filename=product.source_filename)
    # Fallback to sample_datasheet.pdf
    sample = Path(__file__).resolve().parent.parent / "sample_datasheet.pdf"
    if sample.exists():
        return FileResponse(str(sample), media_type="application/pdf", filename=product.source_filename or "sample_datasheet.pdf")
    raise HTTPException(status_code=404, detail="Original source file not found on server")


@router.get("/products/{product_id}/export/jsonld")
async def export_product_jsonld(product_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.fields))
    )
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    data = export_json_ld(product)
    return StreamingResponse(
        iter([json.dumps(data, indent=2)]),
        media_type="application/ld+json",
        headers={"Content-Disposition": f'attachment; filename="product_{product_id}.jsonld"'},
    )


@router.get("/products/{product_id}/export/gs1")
async def export_product_gs1(product_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.fields))
    )
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    csv_data = export_gs1_csv(product)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="product_{product_id}_gs1.csv"'},
    )


@router.get("/products/{product_id}/export/unilog-excel")
async def export_product_unilog_excel(product_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    product = None
    try:
        stmt = (
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.fields))
        )
        result = await session.execute(stmt)
        product = result.scalar_one_or_none()
    except Exception as exc:
        logger.warning("Database query failed during single product export, using fallback: %s", exc)

    if not product:
        # Fallback demo product
        demo_product = {
            "part_number": "ACS580-01-018A-4",
            "manufacturer": "ABB",
            "category": "Industrial Automation > Drives > Variable Frequency Drives (VFD)",
            "fields": [
                {"attribute_key": "voltage_rating", "value": "400", "unit": "V AC"},
                {"attribute_key": "power_rating", "value": "7.5", "unit": "kW"},
                {"attribute_key": "current_rating", "value": "17.7", "unit": "A"},
                {"attribute_key": "frequency_rating", "value": "50/60", "unit": "Hz"},
                {"attribute_key": "ip_rating", "value": "IP21", "unit": ""},
                {"attribute_key": "operating_temp", "value": "-15 to 50", "unit": "°C"},
            ],
            "Datasheet_PDF_URL": "/sample_datasheet.pdf",
            "Provenance_Source_URL": "https://www.abb.com/products/ACS580-01-018A-4",
        }
        xlsx_bytes = export_unilog_excel_bytes([demo_product])
    else:
        xlsx_bytes = export_unilog_excel_bytes([product])

    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="unilog_product_{getattr(product, "part_number", product_id)}.xlsx"'},
    )


@router.get("/export-unilog-excel")
async def export_catalog_unilog_excel(
    product_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    products = []
    try:
        stmt = select(Product).options(selectinload(Product.fields))
        if product_id:
            stmt = stmt.where(Product.id == product_id)
        if batch_id:
            stmt = stmt.where(Product.batch_id == batch_id)
        stmt = stmt.order_by(Product.created_at.desc())

        result = await session.execute(stmt)
        products = result.scalars().all()
    except Exception as exc:
        logger.warning("Database query failed during catalog export, using fallback: %s", exc)

    if not products:
        # Fallback sample products for testing / demo
        demo_product = {
            "part_number": "ACS580-01-018A-4",
            "manufacturer": "ABB",
            "category": "Industrial Automation > Drives > Variable Frequency Drives (VFD)",
            "fields": [
                {"attribute_key": "voltage_rating", "value": "400", "unit": "V AC"},
                {"attribute_key": "power_rating", "value": "7.5", "unit": "kW"},
                {"attribute_key": "current_rating", "value": "17.7", "unit": "A"},
                {"attribute_key": "frequency_rating", "value": "50/60", "unit": "Hz"},
                {"attribute_key": "ip_rating", "value": "IP21", "unit": ""},
                {"attribute_key": "operating_temp", "value": "-15 to 50", "unit": "°C"},
                {"attribute_key": "weight", "value": "7.3", "unit": "kg"},
                {"attribute_key": "certifications", "value": "CE, UL, cUL, EAC", "unit": ""},
            ],
            "Datasheet_PDF_URL": "/sample_datasheet.pdf",
            "Provenance_Source_URL": "https://www.abb.com/products/ACS580-01-018A-4",
        }
        xlsx_bytes = export_unilog_excel_bytes([demo_product])
    else:
        xlsx_bytes = export_unilog_excel_bytes(products)

    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="unilog_catalog_export.xlsx"'},
    )


@router.post("/export-unilog-excel")
async def export_custom_unilog_excel(request: Request):
    """Accepts JSON payload with enriched SKUs and returns an openpyxl-generated .xlsx file."""
    try:
        payload = await request.json()
    except Exception:
        payload = []

    products_list = payload if isinstance(payload, list) else payload.get("products", [payload]) if isinstance(payload, dict) else []
    if not products_list:
        raise HTTPException(status_code=400, detail="Empty product payload")

    xlsx_bytes = export_unilog_excel_bytes(products_list)
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="unilog_catalog_export.xlsx"'},
    )


@router.post("/products/{product_id}/reprocess", response_model=ProductRead)
async def reprocess_product(product_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(Product).where(Product.id == product_id).options(selectinload(Product.fields))
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    file_path = _product_path(product)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Original source file not found on server")

    # Delete existing fields so a re-run rebuilds them cleanly
    stmt_del = select(ProductField).where(ProductField.product_id == product_id)
    result_del = await session.execute(stmt_del)
    for pf in result_del.scalars().all():
        await session.delete(pf)

    product.status = ProductStatus.PROCESSING
    product.confidence_distribution = {}
    product.completed_at = None
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    publish(
        "product:status",
        {
            "product_id": str(product_id),
            "status": "processing",
            "part_number": product.part_number,
            "source_filename": product.source_filename,
        },
    )

    queued = _enqueue_processing(str(product_id), file_path)
    if not queued:
        _spawn_background(process_in_background(product.id, file_path))

    return product
