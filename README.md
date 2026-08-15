# 🛡️ PASTE — Industrial Product Intelligence & Trust Engine

<div align="center">

![PASTE Banner](https://img.shields.io/badge/PASTE-AI%20Product%20Intelligence-059669?style=for-the-badge&logo=shield&logoColor=white)

**Deterministic • Fully Traceable • Zero-Hallucination • Commerce-Ready**

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![VLM](https://img.shields.io/badge/VLM-Qwen2--VL%20%2F%20llama.cpp-7C3AED?style=flat-square)](https://github.com/QwenLM/Qwen2-VL)
[![GS1 Standard](https://img.shields.io/badge/Standards-GS1%20CSV%20%7C%20JSON--LD-F59E0B?style=flat-square)](https://schema.org/Product)
[![Tests Passing](https://img.shields.io/badge/Tests-16%2F16%20Passed-10B981?style=flat-square&logo=pytest&logoColor=white)](tests/test_trust_model.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-gray.svg?style=flat-square)](LICENSE)

[Key Features](#-key-features) • [Architecture](#-system-architecture) • [Trust Model](#-the-mathematical-trust-model) • [Review Console](#-human-in-the-loop-hitl-workspace) • [API Reference](#-api-endpoints) • [Quickstart](#-quickstart--installation)

</div>

---

## 📌 Overview

Industrial manufacturers manage millions of mission-critical product records trapped across heterogeneous datasheets, CAD drawings, ERP dumps, and catalogs. 

Traditional RAG and LLM chatbots often **hallucinate** critical specifications (e.g. converting `24V DC` to `220V AC` or inventing non-existent IP ratings) without any provenance trail. In industrial commerce and procurement, a single incorrect spec can cause equipment destruction, severe safety violations, and costly returns.

**PASTE (Prove · Assert · Separate · Trace · Evaluate)** is a high-precision, deterministic product intelligence engine. Every emitted attribute is categorized into an explicit provenance state (**`PROVED`**, **`INFERRED`**, **`HUMAN`**, or **`UNKNOWN`**), carries a computed confidence score, and contains exact coordinates pointing back to source evidence. The system is architecturally **permitted to refuse** rather than guess.

> 🌟 **Guiding Principle:** *"Never present an inferred value as a fact."*

---

## ✨ Key Features

- 📄 **Multi-Modal Document Ingestion:** Ingests PDF datasheets, CAD exports, technical drawings, images, and raw part numbers. Content is indexed via SHA-256 for strictly idempotent processing.
- 🔬 **Dual-Pass VLM Extraction:** Runs two independent layout-aware extraction passes (via local Qwen2-VL / llama.cpp or rule-based fallback). Discrepancies collapse into a `DISPUTE` state for human sign-off.
- 📐 **Deterministic Normalization:** Automatically standardizes units (`kW → W`, `Celsius → °C`, `bar → Pa`) and aliases to canonical industrial taxonomies.
- 🚫 **Physical Reality Gates:** Validates extracted numbers against strict physical boundaries (voltage envelopes, operating temperatures, IP rating enums).
- 🧩 **Sibling-SKU Knowledge Graph:** Propagates verified series attributes to incomplete sibling records, strictly tagging them as `INFERRED` and capping confidence at $\le 0.70$.
- 🔍 **Exception-Only HITL Review Console:** Side-by-side verification interface where operators inspect document evidence, perform inline corrections, and certify records.
- 📦 **Commerce-Ready Dual Export:** Direct export to **schema.org `JSON-LD`** (with complete provenance trails) and **GS1-compliant CSV** for enterprise PIM/ERP systems.
- ⚡ **Realtime Event Streaming:** Live updates across worker processes and frontend clients using Server-Sent Events (`/api/v1/events`) and Redis Pub/Sub.

---

## 📊 RAG vs. PASTE Comparison

| Feature | Generic RAG / LLM Chatbot | 🛡️ PASTE Engine |
|---|---|---|
| **Missing Attributes** | Hallucinates plausible values with no source | **Graceful refusal; explicitly tagged `UNKNOWN`** |
| **Attribute Provenance** | Unstructured black-box summary | **Document coordinate, page number, authority %** |
| **Physical Validation** | None (allows impossible values) | **Deterministic physical reality boundary checks** |
| **Inferred Sibling Data** | Presented with equal weight as facts | **Explicitly tagged `INFERRED` & capped at ≤0.70** |
| **Contradictory Sources** | Averages conflicting facts together | **Flags `DISPUTE` state $\rightarrow$ routed to human queue** |
| **Export Formats** | Markdown text or arbitrary JSON | **GS1 CSV & schema.org `JSON-LD` native** |

---

## 📐 System Architecture

```
[ Ingest: PDF / Image / Part # / URL ]
                   │
                   ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 1: Ingestion & Content Hashing                  │
│  SHA-256 content addressing • Strictly idempotent      │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 2: Dual-Pass VLM Extraction                     │
│  Qwen2-VL / llama.cpp • 2 independent passes           │
│  Discrepancy detection (1.0 vs 0.4 dispute collapse)  │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 3: Deterministic Normalizer                     │
│  Unit standardization (kW, °C, V, A) • Alias mapping   │
│  Physical constraint validation (enums, ranges)        │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 4: Sibling-SKU Knowledge Graph                  │
│  Propagates verified series attributes to incomplete   │
│  sibling records (strictly INFERRED, capped ≤0.70)     │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 5: Trust Routing Gate & Verification            │
│  conf(field) = Strength × Authority × Agreement        │
└──────────────┬───────────────────┬─────────────────────┘
               │                   │
      conf ≥ 0.90 (PROVED)   Disputes / Inferred / Violations / <0.90
               │                   │
               ▼                   ▼
    ┌──────────────────────┐   ┌────────────────────────────────┐
    │ Auto-Publish Gateway │   │ Human-in-the-Loop (HITL) Queue │
    │ • JSON-LD (Schema)   │   │ • Side-by-side evidence view   │
    │ • GS1 Standard CSV   │   │ • Inline edit, accept, reject  │
    └──────────────────────┘   └────────────────────────────────┘
```

---

## 🎛️ The Mathematical Trust Model

Confidence is **never** generated through prompt estimation. It is calculated via an explicit deterministic formula:

$$\mathbf{Confidence(field) = Extraction\_Strength \times Source\_Authority \times Multi\_Source\_Agreement}$$

### Factor Weights

| Factor | Value | Condition |
|---|:---:|---|
| **Extraction Strength** | `1.0` | Two independent VLM passes agree exactly (Corroborated) |
| | `0.8` | Near-match (normalized numeric/unit equivalence) |
| | `0.5` | Single-pass extraction succeeded |
| | `0.4` | Passes disagree $\rightarrow$ **Forced Human Review / Dispute** |
| **Source Authority** | `1.0` | Official Manufacturer Datasheet / CAD |
| | `0.7` | Distributor / Secondary Catalog |
| | `0.5` | Sibling-SKU Knowledge Graph Inference |
| | `0.3` | Model-predicted estimation |
| **Agreement** | `1.0` | $\ge 2$ Independent sources agree |
| | `0.7` | Single source citation |

### Routing Priority Engine (First Match Wins)
1. **`UNKNOWN`** $\rightarrow$ Never published; marked as insufficient evidence.
2. **Conflicting Sources** $\rightarrow$ **`DISPUTE`** state (never averaged).
3. **Pass Disagreement (`extraction_strength < 0.5`)** $\rightarrow$ Forced Human Review.
4. **`INFERRED`** $\rightarrow$ Confidence hard-capped at **$\le 0.70$**; **never auto-exports**.
5. **Physical Constraint Violation** $\rightarrow$ Forced Human Review.
6. **`conf ≥ 0.90` (PROVED)** $\rightarrow$ **Auto-Approved $\rightarrow$ Export Ready**.
7. **`0.50 ≤ conf < 0.90`** $\rightarrow$ **Borderline Review Queue**.

---

## 🖥️ Human-in-the-Loop (HITL) Workspace

The PASTE Console provides a modern, light-theme interface with an interactive **HTML5 Physics Canvas**:

- **Realtime Telemetry:** Live SSE streaming updates for queue status and background workers.
- **Interactive Confidence Simulator:** Live formula calculator demonstrating exact routing decisions.
- **Side-by-Side Inspector:** Split view comparing raw OCR/VLM document citations against editable canonical fields.
- **Action Certification:** Accept, manually edit (`HUMAN` certification), or reject individual attributes.

---

## 🚀 Quickstart & Installation

### Prerequisites
- Python 3.12+ (or Docker & Docker Compose)
- PostgreSQL 16+ (with `pgvector` extension)

### Model API setup

For AI extraction, add these values to `.env` before starting the app:

```env
MODEL_PROVIDER=openai
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-4o-mini
# Optional: use any OpenAI-compatible endpoint.
# OPENAI_BASE_URL=https://your-provider.example/v1
```

The API performs two independent vision extraction passes and sends disagreements to review. Without `OPENAI_API_KEY`, PDF uploads use the deterministic table/key-value fallback; image uploads require the model API.
### 1. Local Setup

```bash
# Clone the repository
git clone https://github.com/ABHISHEK-DBZ/Aegis-AI.git
cd hackathon-paste

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Start FastAPI application
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 2. Docker Setup

```bash
docker compose up -d --build
```

- **Dashboard UI:** `http://localhost:8000/`
- **Interactive Swagger Docs:** `http://localhost:8000/docs`
- **Realtime SSE Stream:** `http://localhost:8000/api/v1/events`

---

## 📡 API Endpoints

### Ingestion & Products
- `POST /api/v1/products/upload` — Upload datasheet (PDF/Image) with metadata.
- `GET /api/v1/products` — List all products with confidence distributions.
- `GET /api/v1/products/{id}` — Retrieve detailed product record and field provenance.
- `POST /api/v1/products/{id}/reprocess` — Re-run 5-stage pipeline on original source.

### Human-in-the-Loop (HITL) Review
- `GET /api/v1/review/queue` — Query pending review queue with severity filters (`dispute`, `forced_review`, `constraint_violation`, `inferred`, `borderline`).
- `GET /api/v1/review/fields/{field_id}` — Get field-level provenance, citations, and product context.
- `PATCH /api/v1/review/fields/{field_id}` — Accept, edit, or reject an individual attribute.
- `POST /api/v1/review/bulk` — Perform bulk approval/rejection operations.

### Commerce Exports
- `GET /api/v1/products/{id}/export/jsonld` — Export as schema.org `JSON-LD` Product with full provenance metadata.
- `GET /api/v1/products/{id}/export/gs1_csv` — Export as GS1-compliant CSV row.

---

## 🧪 Test Suite

The trust model is verified by a 16-point automated unit test suite covering confidence formulas, all routing rules, unit normalizers, and constraint checks.

```bash
python -m pytest tests/test_trust_model.py -v
```

```
tests/test_trust_model.py::test_confidence_formula PASSED                [  6%]
tests/test_trust_model.py::test_routing_auto_approve PASSED              [ 12%]
tests/test_trust_model.py::test_routing_forced_review_on_disagree PASSED [ 18%]
tests/test_trust_model.py::test_routing_inferred_never_auto PASSED       [ 25%]
tests/test_trust_model.py::test_inferred_cap PASSED                      [ 31%]
tests/test_trust_model.py::test_routing_dispute PASSED                   [ 37%]
tests/test_trust_model.py::test_routing_constraint_violation PASSED      [ 43%]
tests/test_trust_model.py::test_routing_unknown_refusal PASSED           [ 50%]
tests/test_trust_model.py::test_extraction_strength_corroborated PASSED  [ 56%]
tests/test_trust_model.py::test_extraction_strength_disagree PASSED      [ 62%]
tests/test_trust_model.py::test_normalize_unit PASSED                    [ 68%]
tests/test_trust_model.py::test_canonicalize_attribute PASSED            [ 75%]
tests/test_trust_model.py::test_validate_constraints_ip_ok PASSED        [ 81%]
tests/test_trust_model.py::test_validate_constraints_ip_bad PASSED       [ 87%]
tests/test_trust_model.py::test_validate_constraints_voltage_range PASSED [ 93%]
tests/test_trust_model.py::test_normalize_extraction_produces_fields PASSED [100%]

======================= 16 passed in 0.28s ========================
```

---

## 📂 Project Structure

```
├── app/
│   ├── main.py             # FastAPI entrypoint, lifespan, CORS, static routes
│   ├── config.py           # Pydantic settings & environment configuration
│   ├── db.py               # Async SQLAlchemy engine + session factory
│   ├── models.py           # ORM schemas, FieldType enum, Pydantic models
│   ├── trust_model.py      # Mathematical confidence formula & routing engine
│   ├── vlm.py              # Dual-pass VLM client (llama.cpp) & pdfplumber fallback
│   ├── pipeline.py         # Full 5-stage ingestion, normalization & export pipeline
│   ├── routes.py           # Ingestion, products, batches, and export endpoints
│   ├── review_routes.py    # HITL queue, field inspection & audit trail endpoints
│   ├── events.py           # Realtime event bus (SSE + Redis Pub/Sub)
│   └── worker.py           # Background RQ worker for scalable queue processing
├── frontend/
│   └── index.html          # Enterprise Review Console with HTML5 Physics Canvas
├── tests/
│   └── test_trust_model.py # Automated trust model test suite
├── init.sql                # PostgreSQL + pgvector schema initialization
├── docker-compose.yml      # Container orchestration (API, Worker, DB, Redis)
└── requirements.txt        # Production dependencies
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
