Here is the **Architecture Record Document (ARD)** based on the provided Technical Design Document. It breaks down the system into formal Architecture Decision Records (ADRs) to document the *why* and *how* of all major technical choices.

---

# Architecture Record Document (ARD)
**Project Name:** Project Forge (Local AI Coding Agent)
**Date:** October 24, 2023
**Document Version:** 1.0
**Based on TDD Version:** 1.1

## Introduction
This document captures the major architectural decisions made for Project Forge. Each decision is recorded using the standard Architecture Decision Record (ADR) format to provide context, outline the decision, and detail the resulting consequences (trade-offs).

---

## ADR 001: Hub-and-Spoke API Gateway Architecture
**Status:** Accepted

**Context:** 
The system must integrate multiple disparate components: IDE clients (VS Code/JetBrains), a local CI/CD server, a Vector Database (ChromaDB) for RAG, and an LLM Inference Engine. Furthermore, the IDE clients (via the Continue.dev extension) expect a standard OpenAI API format. 

**Decision:** 
We will implement a hub-and-spoke architecture centralized around a custom **Python FastAPI Gateway**. 
*   The Gateway will expose OpenAI-compatible REST endpoints (`/v1/completions`, `/v1/chat/completions`).
*   It will act as an orchestrator, intercepting chat requests to inject RAG context from ChromaDB before forwarding the enriched prompt to the Inference Engine.
*   It will expose dedicated webhook endpoints for CI/CD integration.

**Consequences:**
*   **Positive:** Seamless integration with existing open-source IDE extensions (Continue.dev) without modifying their source code. Centralized logic makes it easy to swap out backend LLMs or Vector DBs in the future.
*   **Negative:** The Gateway becomes a single point of failure and a potential bottleneck if not scaled properly to handle concurrent developer requests.

---

## ADR 002: Selection of Local AI Models
**Status:** Accepted

**Context:** 
Operating in a strict air-gapped environment requires hosting models locally. We need to balance three distinct workloads: real-time code autocomplete (requires < 400ms latency), complex reasoning/chat (requires high accuracy), and codebase indexing (requires accurate vector embeddings). All models must fit within constrained local VRAM.

**Decision:** 
We will deploy three specialized, open-source models:
1.  **Autocomplete (FIM):** `Qwen2.5-Coder-1.5B` (or `StarCoder2-3B`). Chosen for its small VRAM footprint (~2-4GB) and blazing-fast inference speed.
2.  **Chat & Reasoning:** `DeepSeek-Coder-V2-Lite-Instruct` (16B MoE) or `Qwen2.5-Coder-7B-Instruct`. Chosen for top-tier coding benchmarks. Will be quantized (4-bit/8-bit) if necessary to fit within VRAM limits.
3.  **Embeddings (RAG):** `nomic-embed-text` (v1.5) or `bge-m3`. Chosen for high retrieval accuracy on code syntax while consuming < 1GB VRAM.

**Consequences:**
*   **Positive:** Highly optimized user experience. Autocomplete remains fast by bypassing RAG and using a lightweight model, while complex queries get the heavy reasoning model.
*   **Negative:** Running three models concurrently increases the baseline VRAM requirement and operational complexity (managing multiple model weights and inference endpoints).

---

## ADR 003: Hardware Specifications and GPU Provisioning
**Status:** Accepted

**Context:** 
To support the concurrent execution of the three selected models (ADR 002) alongside the FastAPI Gateway and ChromaDB, specific hardware minimums must be established to prevent Out-Of-Memory (OOM) crashes and unacceptable latency.

**Decision:** 
The following hardware specifications are mandated for the host server:
*   **GPU:** Minimum 1x 24GB VRAM (e.g., RTX 3090/4090/A10G). Recommended 2x 24GB or 1x 48GB VRAM (e.g., RTX 6000 Ada) for teams > 10 developers to handle KV Cache for concurrent requests.
*   **CPU:** Minimum 8 Cores / 16 Threads (Recommended: 16C/32T) for Git cloning, text chunking, and API routing.
*   **RAM:** Minimum 32 GB DDR4 (Recommended: 64 GB DDR5).
*   **Storage:** Minimum 500 GB NVMe SSD (Recommended: 1 TB+ Gen4 NVMe) for fast loading of `.gguf`/`.safetensors` weights into VRAM.

**Consequences:**
*   **Positive:** Guarantees the system can hold the ~14GB Chat model, ~3GB Autocomplete model, and <1GB Embedding model simultaneously while leaving room for context windows.
*   **Negative:** High upfront capital expenditure (CapEx) for hardware procurement.

---

## ADR 004: Air-Gapped Deployment & Model Ingestion Protocol
**Status:** Accepted

**Context:** 
The lab environment has zero internet access. Standard deployment practices (e.g., `docker pull`, downloading weights directly from HuggingFace via API) will fail.

**Decision:** 
The entire stack will be containerized using **Docker Compose**. 
*   Docker images (`vllm/vllm-openai`, `chromadb/chroma`, and the custom Gateway) will be saved as tarballs, transferred via USB/data diode, and loaded locally.
*   Model weights (`.gguf` / `.safetensors`) will follow a strict manual ingestion protocol: Download externally -> Malware/Hash Scan -> Transfer via USB/Diode -> Mount to `/mnt/data/models` -> Restart containers.
*   vLLM will be configured with `--gpu-memory-utilization 0.85` to prevent hard OOM crashes.

**Consequences:**
*   **Positive:** 100% compliance with strict security and air-gap constraints. No risk of proprietary code leaking to external APIs.
*   **Negative:** Updates to models or system components are highly manual, slowing down the adoption of newer, better LLMs as they are released.

---

## ADR 005: CI/CD Automated Debugging Integration
**Status:** Accepted

**Context:** 
Developers spend significant time debugging failed CI/CD pipelines. We want to leverage the local LLM to analyze build failures automatically.

**Decision:** 
The FastAPI Gateway will expose a webhook endpoint (`/api/v1/ci/webhook`). 
*   When a build fails, the local CI server (GitLab/Gitea) will push a payload containing the truncated tail of the error log (max 3,000 tokens).
*   The Gateway will asynchronously process this log, query the Chat LLM (`DeepSeek-Coder-V2-Lite-Instruct`) for a fix, and post the suggested fix back to the Pull Request/Merge Request via the Git server's REST API.

**Consequences:**
*   **Positive:** Drastically reduces developer debugging time by providing immediate, AI-generated context and fixes directly in the PR.
*   **Negative:** Requires custom webhook configuration on the CI server. Truncating logs to 3,000 tokens means the LLM might miss the root cause if the actual error occurred earlier in the build output.