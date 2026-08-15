# 🛡️ PASTE — AI-Powered Product Intelligence & Trust Engine

<div align="center">

![PASTE Banner](https://img.shields.io/badge/PASTE-AI%20Product%20Intelligence-059669?style=for-the-badge&logo=shield&logoColor=white)

**Deterministic • Traceable • Zero-Hallucination • Commerce-Ready**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17%20%2B%20pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![VLM](https://img.shields.io/badge/VLM-Qwen2--VL%20%2F%20llama.cpp-7C3AED?style=flat-square)](https://github.com/QwenLM/Qwen2-VL)
[![GS1](https://img.shields.io/badge/Export-GS1%20CSV%20%26%20JSON--LD-F59E0B?style=flat-square)](https://schema.org/Product)
[![Tests](https://img.shields.io/badge/Tests-16%2F16%20Passed-10B981?style=flat-square&logo=pytest&logoColor=white)](tests/test_trust_model.py)

[⚡ Quickstart](#-quickstart) • [📐 Architecture](#-5-stage-pipeline-architecture) • [🎛️ Trust Formula](#-mathematical-trust-model) • [🖥️ Dashboard](#-human-in-the-loop-hitl-review-console) • [📊 RAG vs PASTE](#-why-generic-rag-fails-in-industrial-commerce)

</div>

---

## 🎯 Executive Summary & The Problem

Industrial manufacturers manage millions of mission-critical SKUs trapped inside unstructured PDFs, CAD exports, vendor ERP sheets, and photos. 

- **The Danger of RAG Chatbots:** Generic LLMs and vector RAG **hallucinate** specifications (e.g. guessing `24V DC` instead of `220V AC`, or inventing non-existent IP ratings) with zero provenance. In industrial operations, **one wrong spec destroys machinery or causes catastrophic safety hazards**.
- **The PASTE Solution:** Every single attribute is tagged **`PROVED`**, **`INFERRED`**, **`HUMAN`**, or **`UNKNOWN`**. Every spec carries a mathematical confidence score and coordinates pointing back to source evidence. The system is explicitly **allowed to refuse** rather than hallucinate.

> 🌟 **North Star:** *"Never present an inferred value as a fact."*

---

## ⚖️ Why Generic RAG Fails in Industrial Commerce

| Capability | Generic RAG / LLM Chatbot | 🛡️ PASTE Trust Engine |
|---|---|---|
| **Missing Attributes** | ❌ Hallucinates plausible values with no source | ✅ **Refuses gracefully; tagged `UNKNOWN`** |
| **Attribute Provenance** | ❌ Black-box summary with no citations | ✅ **Page number, layout bounding box, authority %** |
| **Physical Validation** | ❌ Allows absurd inputs (e.g. 100,000V DC sensor) | ✅ **Deterministic industrial physical reality gates** |
| **Inferred Sibling Data** | ❌ Blurs facts and guesses together | ✅ **Explicitly tagged `INFERRED` & capped at ≤0.70** |
| **Conflicting Sources** | ❌ Averages conflicting values into wrong data | ✅ **Flags `DISPUTE` state → routes to human queue** |
| **Export Formats** | ❌ Unstructured markdown / plain text | ✅ **GS1 CSV & schema.org `JSON-LD` native** |

---

## 📐 5-Stage Pipeline Architecture

```
[ Ingest Studio: PDF / image / part # ]
                   │
                   ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 1: Ingest & Content-Hash                        │
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
│  Unit conversion (kW→W, °C, V, A) • Alias mapping       │
│  Physical constraint validation (enums, voltage bounds)│
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
│  Computes conf(field) = Strength × Authority × Agree   │
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

## 🎛️ Mathematical Trust Model

Confidence is **never** estimated by prompt engineering. It is calculated via an explicit deterministic formula:

$$\mathbf{Confidence(field) = Extraction\_Strength \times Source\_Authority \times Multi\_Source\_Agreement}$$

### 1. Factor Weights Table

| Factor | Value | Condition |
|---|:---:|---|
| **Extraction Strength** | `1.0` | Two independent VLM passes agree exactly (Corroborated) |
| | `0.8` | Near-match (numerical/unit normalized equivalence) |
| | `0.5` | Single-pass extraction succeeded |
| | `0.4` | Passes disagree → **Forced Human Review / Dispute** |
| **Source Authority** | `1.0` | Official Manufacturer Datasheet / CAD |
| | `0.7` | Distributor / Secondary Catalog |
| | `0.5` | Sibling-SKU Knowledge Graph Inference |
| | `0.3` | Model-predicted estimation |
| **Agreement** | `1.0` | $\ge 2$ Independent sources agree |
| | `0.7` | Single source citation |

### 2. Gating & Routing Priority Rules
1. **`UNKNOWN`** $\rightarrow$ Never published; displayed as insufficient evidence.
2. **Pass Disagreement (`extraction_strength < 0.5`)** $\rightarrow$ Forced Human Review.
3. **`INFERRED`** $\rightarrow$ Confidence hard-capped at **$\le 0.70$**; **never auto-exports**.
4. **Conflicting Sources** $\rightarrow$ **`DISPUTE`** state (never averaged).
5. **Physical Constraint Violation** $\rightarrow$ Forced Human Review.
6. **`conf ≥ 0.90` (PROVED)** $\rightarrow$ **Auto-Approved $\rightarrow$ Export Ready**.
7. **`0.50 ≤ conf < 0.90`** $\rightarrow$ **Borderline Review Queue**.

---

## 🖥️ Human-in-the-Loop (HITL) Review Console

The PASTE Frontend is built with an **enterprise-grade light aesthetic** and a **live HTML5 Physics Canvas**:

<div align="center">

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  PASTE Engine v1.1     [Overview] [5-Stage] [Calculator] [HITL Queue (3)]  ● Live│
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   PRODUCT REVIEW: Acme Industrial Motor X-100                                    │
│   Manufacturer: Acme Industrial  •  Total Fields: 7                              │
│                                                                                  │
│  ┌───────────────────────────────┐  ┌─────────────────────────────────────────┐  │
│  │ DOCUMENT PROVENANCE           │  │ FIELD SPECIFICATION & CERTIFICATION     │  │
│  │                               │  │                                         │  │
│  │ page_1 (Authority: 100%)      │  │ Voltage Rating [PROVED] [95% AUTO]      │  │
│  │ ┌───────────────────────────┐ │  │ [ 220V AC       ] [ V                 ] │  │
│  │ │ Rated Voltage: 220V AC    │ │  │                                         │  │
│  │ │ Rated Current: 4.5A       │ │  │ Operating Temperature [PROVED] [95%]    │  │
│  │ │ Operating Temp: -20~70°C  │ │  │ [ -20 to 70°C   ] [ °C                ] │  │
│  │ └───────────────────────────┘ │  │                                         │  │
│  │                               │  │ Mounting Flange [INFERRED] [65% REVIEW] │  │
│  │ Sibling KG Ref: X-105         │  │ [ B14 Face      ] [                   ] │  │
│  │ Inferred flange geometry      │  │ [ Accept ]  [ Save & Certify ] [ Reject]│  │
│  └───────────────────────────────┘  └─────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

</div>

### Frontend Features:
- ⚛️ **Interactive Node Physics Canvas:** Real-time dynamic visual mesh representing attribute extraction and verification forces.
- 🎛️ **Live Confidence Simulator:** Interactive tactile controls that simulate the mathematical formula in real-time.
- 📋 **Exception-Only HITL Queue:** Filter by *Dispute, Inferred, Constraint Alert, Borderline*.
- 🔍 **Side-by-Side Detail Inspector:** Compare raw extracted OCR/VLM snippets against editable canonical fields.
- 📡 **Live Real-time Telemetry:** Instant queue updates over Server-Sent Events (`/api/v1/events`).

---

## ⚡ Quickstart

### Prerequisites
- Python 3.12+ (or Docker & Docker Compose)
- PostgreSQL 16+ (with `pgvector` enabled)

### Option A: Local Dev (Recommended)

```bash
# 1. Clone repository
git clone https://github.com/ABHISHEK-DBZ/Aegis-AI.git
cd hackathon-paste

# 2. Set up virtual environment
python -m venv .venv
.venv/Scripts/activate  # On Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# 3. Environment configuration
cp .env.example .env

# 4. Start local PostgreSQL cluster & run server
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Option B: Docker Compose

```bash
docker compose up -d --build
```

---

## 🧪 Smoke Test & Verification

### 1. Ingest a Sample Technical Datasheet
```bash
curl -X POST http://localhost:8000/api/v1/products/upload \
  -F "file=@sample_datasheet.pdf" \
  -F "manufacturer=Acme Industrial" \
  -F "part_number=X-100"
```

### 2. Check Review Queue
```bash
curl http://localhost:8000/api/v1/review/queue
```

### 3. Export Commerce-Ready Records
```bash
# JSON-LD (schema.org/Product with full provenance)
curl http://localhost:8000/api/v1/products/{product_id}/export/jsonld

# GS1-Compliant CSV
curl http://localhost:8000/api/v1/products/{product_id}/export/gs1_csv
```

### 4. Run Automated Test Suite
```bash
.venv/Scripts/python -m pytest tests/test_trust_model.py -v
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

======================= 16 passed, 4 warnings in 4.13s ========================
```

---

## 📂 Repository Structure

```
├── app/
│   ├── main.py             # FastAPI entrypoint, lifespan, CORS, static routes
│   ├── config.py           # Pydantic settings & environment configuration
│   ├── db.py               # Async SQLAlchemy engine + session factory
│   ├── models.py           # ORM schemas, FieldType, and Pydantic models
│   ├── trust_model.py      # Mathematical confidence formula & routing engine
│   ├── vlm.py              # 2-Pass VLM client (llama.cpp) & pdfplumber fallback
│   ├── pipeline.py         # Full 5-stage ingestion, normalization & export
│   ├── routes.py           # Ingestion, products, batches, and export routes
│   ├── review_routes.py    # HITL queue, field-level inspection & certification
│   ├── events.py           # Realtime event bus (SSE + Redis Pub/Sub)
│   └── worker.py           # Background RQ worker for scalable queue processing
├── frontend/
│   └── index.html          # Enterprise Light Review Dashboard with Physics Canvas
├── tests/
│   └── test_trust_model.py # Comprehensive 16-point trust model unit test suite
├── PASTE-PRD.md            # Complete Product Requirement Document
├── docker-compose.yml      # Multi-container orchestration (API, Worker, DB, Redis)
└── requirements.txt        # Python production dependencies
```

---

## 🏆 Hackathon Demo Script (3-Minute Judge Walkthrough)

1. **The Core Hook:** Show the interactive confidence simulator on the home page — drag sliders to demonstrate how conflicting passes collapse into `DISPUTE`.
2. **1-Click Ingest:** Click **"Run Acme X-100 Demo Ingest"** to parse the datasheet across the 5-stage deterministic engine.
3. **Inspect Provenance:** Navigate to the **HITL Review Queue**, click on an attribute, and showcase the exact PDF page citation and authority score.
4. **Export Commerce Ready:** Trigger the **JSON-LD / GS1 CSV** export to demonstrate zero-friction PIM/ERP readiness.

---

<div align="center">

**Built for the Industrial Commerce AI Hackathon**  
*PASTE: Prove • Assert • Separate • Trace • Evaluate*

</div>
