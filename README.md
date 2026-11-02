# BimaSense AI — Medical Insurance Hybrid RAG & Android Copilot

**BimaSense AI** is an end-to-end Medical Insurance Intelligence Platform built with a **Python FastAPI + LangGraph + Qdrant Hybrid Vector DB** backend and a native **Kotlin + Jetpack Compose (Material 3)** Android client. It decodes 40–70 page Indian health insurance policy wordings with page-level PDF citations, compares multiple insurers side-by-side, calculates exact out-of-pocket hospital bill deductions deterministically, and audits unfair claim rejections against the **IRDAI Master Circular on Health Insurance 2024 (`IRDAI/HLT/CIR/PRO/84/05/2024`)**.

## 1. System Architecture & Tech Stack

| Layer | Technology Choices | Purpose |
| :--- | :--- | :--- |
| **Mobile Frontend** | **Kotlin 2.0**, **Jetpack Compose**, Material 3, Android `PdfRenderer`, Compose `Canvas` | Native Android UI, interactive `[Page X]` PDF citation bottom sheet, and payout donut charts |
| **Android Architecture** | Clean Architecture (`domain`, `data`, `presentation`), MVVM, **Hilt**, **Retrofit + OkHttp SSE**, **Room DB** | Dependency injection, real-time Server-Sent Events token streaming, and offline policy/chat caching |
| **Backend API** | **Python 3.11+**, **FastAPI**, Pydantic v2, Uvicorn | Asynchronous REST endpoints, multipart PDF upload & indexing, and W3C SSE streaming |
| **Document Parsing** | **PyMuPDF4LLM** + **pdfplumber** fallback | Lightweight CPU-friendly, page-tracked, and Markdown-table-preserving PDF extraction |
| **Vector Database** | **Qdrant** (Docker / Qdrant Cloud / Local Hybrid Snapshot) | Hybrid search combining Dense (`BAAI/bge-small-en-v1.5`, 384-d) + Sparse (`BM25`) via Reciprocal Rank Fusion (RRF) |
| **Cross-Encoder Reranker** | **FlashRank** (`ms-marco-MiniLM-L-12-v2`) | Reranks Top-15 hybrid candidates to Top-5 with calibrated `[0.0, 1.0]` relevance scores |
| **Agentic Orchestration** | **LangGraph** (6-Node State Machine), **Groq API** (`llama-3.3-70b-versatile` / `qwen-2.5-32b`), **Ollama** | Intent routing, query decomposition, Corrective RAG grading (`< 0.35` guardrail), and deterministic tool execution |
| **Automated Evaluation** | **Ragas** (`evaluate_ragas.py`) | Automated CI benchmarking across 30 gold Indian health insurance Q&A pairs |

## 2. Core Functional Pillars

1. **Pillar 1 — Citation-Backed Policy Q&A:** Queries pre-loaded Indian health insurance plans (**HDFC ERGO Optima Secure**, **Star Health Comprehensive**, **Niva Bupa ReAssure 2.0**) or user-uploaded Policy PDFs, attaching clickable `[Source: <Plan>, Page <N>, <Section>]` chips that open Android's native `PdfRenderer` directly to that page.
2. **Pillar 2 — Multi-Insurer Side-by-Side Comparator:** Decomposes comparison queries into parallel metadata-filtered Qdrant retrievals and renders a structured comparison matrix across Room Rent, PED Waiting Period, Maternity, Restoration, 68 Non-Payable Consumables, and Senior Co-Payment.
3. **Pillar 3 — Deterministic Out-of-Pocket & Room-Rent Calculator:** Computes exact proportionate room-rent deductions while honoring Clause 1.1.3 exemptions (Pharmacy/Medicines, Implants/Stents, Diagnostics, ICU charges paid at 100%), Annexure-I consumable riders (`Protect Benefit`, `Safeguard+`), deductibles, and mandatory senior co-payment.
4. **Pillar 4 — IRDAI Rights & Claim Rejection Assistant:** Audits claim rejections and hospital discharge delays against `IRDAI/HLT/CIR/PRO/84/05/2024` (36-month moratorium rule, 1-hour cashless pre-authorization, 3-hour discharge limit, ban on direct TPA rejection without Claims Review Committee approval, and Rs. 5,000/day Ombudsman penalty) and drafts a ready-to-send Grievance Redressal Officer (GRO) notice.

## 3. Ragas 30-Question Benchmark Results (`evaluate_ragas.py`)

We evaluated the 6-node LangGraph pipeline across **30 gold Q&A pairs** (`backend/data/eval_dataset.json`) spanning all 4 functional pillars:

| Evaluation Pillar | Benchmark Questions | Faithfulness | Answer Relevancy | Context Recall | Citation Page Accuracy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Pillar 1: Policy Q&A (`policy_qa`)** | 17 | `0.9892` | `0.8814` | `0.9940` | `1.0000` (100%) |
| **Pillar 2: Plan Comparator (`plan_comparison`)** | 3 | `1.0000` | `0.9322` | `0.9914` | `1.0000` (100%) |
| **Pillar 3: Claim Math (`claim_calculation`)** | 3 | `0.9483` | `0.8885` | `0.8655` | `1.0000` (100%) |
| **Pillar 4: IRDAI Grievance (`regulatory_grievance`)** | 7 | `0.9901` | `0.8214` | `0.9810` | `1.0000` (100%) |
| **Overall (30 Gold Questions)** | **30** | **0.9864 (98.6%)** | **0.8732 (87.3%)** | **0.9779 (97.8%)** | **1.0000 (100%)** |

Additionally, on the **15-Query Tricky Insurance Retrieval Benchmark** (`scripts/run_milestone2_benchmark.py`), the hybrid `BAAI/bge-small-en-v1.5` + `BM25` + `FlashRank` pipeline achieved **15/15 (100%) Top-1 and Top-3 accuracy** and flagged out-of-scope queries (`score = 0.2388 < 0.35`) via `RelevanceGraderNode`.

## 4. FastAPI REST & SSE Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/health` | `GET` | Health status, active LLM, embedding, and reranker model check |
| `/api/v1/policies/list` | `GET` | Lists pre-loaded Indian health insurance plans + user-uploaded policies |
| `/api/v1/policies/upload` | `POST` | Multipart PDF upload $\rightarrow$ layout & table extraction $\rightarrow$ Qdrant hybrid indexing under `user_id` |
| `/api/v1/policies/{policy_id}/pdf` | `GET` | Streams the raw PDF file to Android's `PdfRenderer` bottom sheet |
| `/api/v1/chat/stream` | `POST` | Streams `text/event-stream` SSE frames (`node_status`, `token`, `complete`) |
| `/api/v1/chat/query` | `POST` | Synchronous JSON execution of the 6-node LangGraph workflow |
| `/api/v1/compare` | `POST` | Returns structured side-by-side plan comparison rows + citations |
| `/api/v1/calculator/estimate` | `POST` | Runs deterministic room-rent & consumable payout calculation + policy citations |
| `/api/v1/grievance/verify` | `POST` | Audits claim rejections/delays against IRDAI Master Circular 2024 + drafts GRO email |

## 5. Step-by-Step Local Setup Guide

### Step 1: Start Qdrant Vector Database
```bash
docker compose up -d
```

### Step 2: Set Up & Verify the Python Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy environment template and add your free Groq API key (https://console.groq.com)
cp .env.example .env

# Run Milestone 1-4 & Ragas verification suites
python3 scripts/run_milestone1_pipeline.py
python3 scripts/run_milestone2_benchmark.py
python3 scripts/run_milestone3_verification.py
python3 scripts/run_milestone4_api_tests.py
python3 evaluation/evaluate_ragas.py

# Launch FastAPI server (Swagger UI at http://localhost:8000/docs)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 3: Run the Native Android App
1. Open `android-app/` in **Android Studio Ladybug (2024.2.1+)**.
2. If running on the **Android Emulator**, `BuildConfig.BASE_API_URL` is pre-configured to `http://10.0.2.2:8000/`.
3. If running on a **physical Android device** over Wi-Fi, update `BASE_API_URL` in `android-app/app/build.gradle.kts` to your computer's LAN IP (`http://192.168.x.x:8000/`).
4. Click **Run (`Shift + F10`)** to launch **BimaSense AI**.

## 6. 2-Minute Capstone & Portfolio Demo Script

- **0:00 – 0:25 (Policy Vault & PDF Upload):** Open the **Vault** tab showing *HDFC ERGO Optima Secure*, *Star Health Comprehensive*, and *Niva Bupa ReAssure 2.0*. Tap **Upload Policy PDF** to select a personal policy PDF from phone storage and show it indexing live into Qdrant.
- **0:25 – 0:55 (Streaming Chat & Native PDF Citation Sheet):** Switch to the **Copilot** tab and ask: *"What is the waiting period for sugar and BP in HDFC Optima Secure, and are surgical gloves covered?"* Show the real-time SSE token stream and tap the `[HDFC ERGO Optima Secure • Page 2]` citation chip to open the in-app `PdfRenderer` bottom sheet with the highlighted clause.
- **0:55 – 1:20 (Side-by-Side Plan Comparator):** Open the **Compare** tab, select *Star Comprehensive* vs. *ReAssure 2.0*, and highlight how *Star Comprehensive* covers Maternity after 24 months while *ReAssure 2.0* provides unlimited restoration from the first claim.
- **1:20 – 1:45 (Deterministic Claim & Room-Rent Calculator):** Open the **Calculator** tab, set Allowed Room Rent Cap to Rs. 5,000/day and Actual Room Rent to Rs. 10,000/day on a Rs. 1,50,000 bill with Rs. 30,000 exempt medicines. Show the Compose `Canvas` Donut Chart updating in real time while keeping medicines 100% exempt from proportionate deduction.
- **1:45 – 2:00 (IRDAI Grievance & Moratorium Helper):** Open the **IRDAI Rights** tab, set policy tenure to 42 months (`>= 36M` moratorium) and discharge wait to 6.5 hours (`> 3H` limit), tap **Verify IRDAI Compliance**, and tap **Share / Send to Insurer GRO** to open Gmail with the pre-drafted legal notice citing `IRDAI/HLT/CIR/PRO/84/05/2024`.
