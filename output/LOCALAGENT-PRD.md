Here is a comprehensive Technical Product Requirements Document (PRD) tailored for your specific use case. 

---

# Technical Product Requirements Document (PRD)
**Product Name:** Project Forge (Local AI Coding Agent)
**Document Version:** 1.0
**Date:** October 24, 2023
**Author:** [Your Name], Product Owner

## 1. Executive Summary
**Project Forge** is a fully self-hosted, air-gapped AI coding assistant designed for a secure lab environment. It provides a small team of software engineers with state-of-the-art AI code generation, refactoring, and debugging capabilities without requiring external internet access. Furthermore, it integrates directly with the lab’s existing Continuous Integration (CI) infrastructure to automatically analyze failed builds and suggest fixes.

## 2. Problem Statement
Software engineers in secure, air-gapped lab environments cannot utilize cloud-based AI coding assistants (like GitHub Copilot or ChatGPT) due to strict data exfiltration and network security policies. This creates a productivity gap. The team needs a local alternative that respects network boundaries while providing context-aware coding assistance and CI pipeline support.

## 3. Target Audience
*   **Lab Software Engineers (Primary):** ~3-10 developers writing, testing, and debugging code.
*   **DevOps / Lab Admins (Secondary):** Managing the CI pipeline and local infrastructure.

## 4. Key Constraints & Assumptions
*   **Strict Air-Gap:** The system must function with **zero** outbound or inbound internet access. All models, dependencies, and telemetry must remain on the Local Area Network (LAN).
*   **Hardware Availability:** The lab has (or will procure) at least one dedicated server with a capable GPU (e.g., NVIDIA RTX 4090, A6000, or A100) to host the Large Language Model (LLM).
*   **Low Maintenance:** Because the team is small, the infrastructure must be easy to deploy (Dockerized) and require minimal ongoing maintenance.

## 5. Core Features (MVP)

### 5.1. IDE Integration (The "Copilot" Experience)
*   **Inline Code Completion:** Real-time, low-latency code suggestions as the engineer types.
*   **In-IDE Chat:** A chat panel within the IDE (VS Code / JetBrains) to ask questions, generate boilerplate, and refactor highlighted code.
*   **Context Awareness:** The agent can read the currently open files and local workspace to provide relevant answers.

### 5.2. CI/CD Pipeline Integration
*   **Automated Log Analysis:** When a CI build or test fails, the agent automatically ingests the error logs.
*   **Actionable Fix Suggestions:** The agent posts a summary of *why* the build failed and provides a code snippet to fix it (via a comment on the local Git server's Pull Request/Merge Request).

### 5.3. Local Codebase RAG (Retrieval-Augmented Generation)
*   **Repository Indexing:** The system indexes the lab’s local Git repositories so engineers can ask global questions (e.g., *"Where is the authentication middleware defined?"*).

## 6. Technical Architecture & Requirements

To achieve this without internet access, we will utilize an open-source stack.

### 6.1. Backend Infrastructure (The AI Server)
*   **LLM Hosting Engine:** `Ollama` or `vLLM` (Optimized for local inference).
*   **Primary LLM (Chat & Complex Logic):** `DeepSeek-Coder-V2-Lite` or `Llama-3-8B-Instruct` (Requires ~8-16GB VRAM).
*   **Secondary LLM (Fast Autocomplete):** `StarCoder2-3B` or `Qwen2.5-Coder-1.5B` (Requires ~4GB VRAM, optimized for low latency).
*   **Vector Database (For RAG):** `ChromaDB` or `Milvus` (Local Docker container).

### 6.2. Frontend / Client Side (The IDE)
*   **IDE Extension:** `Continue.dev` or `Twinny`. Both are open-source extensions for VS Code and JetBrains that can be configured to point to a local IP address instead of cloud APIs.
*   **Configuration:** Extensions will be pre-configured via a shared JSON file pointing to `http://<lab-ai-server-ip>:<port>`.

### 6.3. CI/CD Integration
*   **Webhook Listener:** A lightweight Python FastAPI service that listens for webhooks from the local Git/CI server (e.g., local GitLab, Gitea, or Jenkins).
*   **Workflow:**
    1. CI Pipeline fails.
    2. CI sends webhook + logs to FastAPI service.
    3. FastAPI service prompts the local LLM with the logs.
    4. FastAPI service pushes the LLM's suggested fix back to the Git server as a PR comment.

## 7. Security & Compliance
*   **Network:** The AI server will be hosted on the lab's internal subnet. Firewall rules will explicitly block all WAN access to and from this server.
*   **Data Privacy:** No code snippets, prompts, or telemetry will leave the lab. 
*   **Model Updates:** Model weights (`.gguf` or `.safetensors` files) will be downloaded on an internet-connected machine, transferred via secure USB/secure file transfer protocol to the lab, and loaded manually.

## 8. Implementation Phases

### Phase 1: Infrastructure & Autocomplete (Weeks 1-2)
*   Procure/allocate GPU server.
*   Install Docker, NVIDIA Drivers, and Ollama/vLLM.
*   Transfer model weights to the air-gapped environment.
*   Install `Continue.dev` on engineer IDEs and point to the local server.
*   *Goal: Engineers have basic chat and autocomplete working.*

### Phase 2: Codebase Context / RAG (Weeks 3-4)
*   Deploy ChromaDB.
*   Set up a script to clone local repositories and embed the codebase into the vector database.
*   Connect the IDE extension to the local RAG pipeline.
*   *Goal: Engineers can ask questions about the entire codebase.*

### Phase 3: CI Integration (Weeks 5-6)
*   Develop the FastAPI webhook listener.
*   Integrate with local Jenkins/GitLab CI.
*   Format LLM outputs to post cleanly as Markdown comments on Merge Requests.
*   *Goal: Failed builds automatically receive AI-generated debugging comments.*

## 9. Success Metrics
*   **Adoption Rate:** 100% of the lab engineers install and keep the IDE extension active.
*   **Latency:** Autocomplete suggestions appear in `< 400ms`.
*   **CI Resolution Time:** Time taken to resolve broken CI builds decreases by 20%.
*   **System Uptime:** The local AI server maintains 99% uptime during lab working hours.

## 10. Open Questions / Action Items
1.  **Hardware:** What is the exact GPU VRAM currently available in the lab? *(Action: DevOps to confirm. If < 16GB, we must use smaller, quantized models).*
2.  **CI Tooling:** Which specific CI tool is currently running in the lab (Jenkins, GitLab CI, TeamCity)? *(Action: Engineering lead to confirm for Phase 3 API integration).*
3.  **IDE Standardization:** Are all engineers using VS Code, or do we need to support JetBrains/Vim as well? *(Action: Product Owner to poll the team).*