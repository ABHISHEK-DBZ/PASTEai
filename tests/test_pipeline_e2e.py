"""End-to-end pipeline test: sample PDF → normalize → route → persist → export.

Uses the rule-based fallback (no VLM model required) to prove the full
extract→normalize→route→persist→export flow against a real Postgres.
"""
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import session_context, init_db
from app.models import Product, ProductField, ProductStatus
from app.pipeline import process_product, export_json_ld, export_gs1_csv


SAMPLE = Path(__file__).parent.parent / "sample_datasheet.pdf"


async def run():
    await init_db()
    pid = uuid.uuid4()
    async with session_context() as session:
        prod = Product(
            source_filename="sample_datasheet.pdf",
            source_hash="test-" + str(pid)[:8],
            source_type="pdf",
            part_number="X-100",
            manufacturer="Acme Industrial",
            category="motors",
            status=ProductStatus.PENDING,
        )
        session.add(prod)
        await session.flush()
        product_id = str(prod.id)

    # Full pipeline (rule-based fallback — no VLM model needed)
    async with session_context() as session:
        await process_product(product_id, SAMPLE, session)

    # Verify
    async with session_context() as session:
        res = await session.execute(select(ProductField).where(ProductField.product_id == product_id))
        fields = res.scalars().all()
        res2 = await session.execute(
            select(Product).where(Product.id == product_id).options(selectinload(Product.fields))
        )
        product = res2.scalar_one()

        print(f"\n=== PRODUCT {product_id} (status={product.status.value}) ===")
        for f in fields:
            print(f"  {f.attribute_key}: {f.value} {f.unit} [{f.field_type.value}] conf={f.confidence:.2f}")
        assert len(fields) >= 5, f"Expected >=5 fields, got {len(fields)}"

        jld = export_json_ld(product)
        assert "schema:Product" in jld["@type"], "JSON-LD malformed"
        csv = export_gs1_csv(product)
        assert "Product_Name" in csv, "GS1 CSV missing header"
        print(f"\nExport OK: JSON-LD fields={len(jld.get('paste:fields', []))}, CSV lines={len(csv.splitlines())}")
        print("E2E PIPELINE PASS")
        return True


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(run()) else 1)
