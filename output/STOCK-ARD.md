Here is the Architecture Record Document (ARD) capturing the major architectural decisions introduced in the updated Technical Design Document.

---

# 🏛️ Architecture Record Document (ARD)

**ARD ID:** ARD-001
**Title:** Adoption of Multi-Agent Orchestration using Google Gemini
**Date:** October 24, 2023
**Status:** **Accepted**
**Architect:** Lead Architect

## 1. Context & Problem Statement
The StockSense AI MVP requires a backend system capable of fetching real-time market data and news, analyzing it, and returning a structured financial recommendation to the frontend. 

Initially, a single-prompt approach using OpenAI (`gpt-4o-mini`) was considered. However, relying on a single prompt to process disparate data types (quantitative price action vs. qualitative news sentiment) increases the risk of LLM hallucinations, diluted reasoning, and poor output structuring. Furthermore, the system must strictly adhere to two primary KPIs:
1.  **Latency:** End-to-end response time must be **< 8 seconds**.
2.  **Cost:** AI inference cost must remain **< $0.02 per query**.

We need an architecture that improves reasoning quality without breaching our latency and cost constraints.

## 2. Decision
We will transition from a single-prompt OpenAI architecture to a **Multi-Agent Orchestration Workflow** powered by **Google Gemini (`gemini-1.5-flash`)**. 

Specifically, we are deciding to:
1.  **Adopt Gemini 1.5 Flash:** Replace OpenAI with Google's `gemini-1.5-flash` due to its superior inference speed, cost-effectiveness, and native support for strict JSON schema enforcement via Pydantic models.
2.  **Implement Persona-Driven Agents:** Break down the analysis into three distinct AI agents with specific personas to enforce separation of concerns:
    *   *Quantitative Analyst Agent:* Focuses strictly on numerical market data.
    *   *News Sentiment Analyst Agent:* Focuses strictly on qualitative news headlines.
    *   *Lead Portfolio Manager (Orchestrator):* Synthesizes the sub-agent reports into a final JSON recommendation.
3.  **Utilize Concurrent Orchestration:** Leverage Python's `asyncio` (via FastAPI) to execute data fetching and sub-agent processing (Quant & News) in parallel, before passing the results to the Orchestrator.

## 3. Justification
*   **Quality of Reasoning:** By assigning strict personas, the LLM is less likely to conflate technical data with fundamental news. The Orchestrator acts as a final logic gate, improving the reliability of the recommendation.
*   **Latency Compliance:** Running the Quant and News agents sequentially would breach the 8-second limit. By using `asyncio.gather`, we parallelize the heaviest workloads. `gemini-1.5-flash` is specifically optimized for high-speed inference, allowing the 3-step agentic workflow to complete within a ~7.0-second budget.
*   **Cost Compliance:** `gemini-1.5-flash` is highly cost-efficient, easily keeping the multi-agent workflow under the $0.02/query limit, even with three separate API calls per request.
*   **System Stability:** Gemini's native `response_schema` parameter allows us to pass our Pydantic `AIAnalysis` model directly to the API, guaranteeing that the Orchestrator outputs perfectly formatted JSON for the frontend, eliminating parsing errors.

## 4. Consequences & Trade-offs

### Positive Impacts (Pros)
*   **Higher Accuracy:** Separation of concerns reduces hallucinations.
*   **Resilience:** The system can gracefully degrade. If the News API or News Agent fails, the Orchestrator can still generate a recommendation based solely on the Quant Agent's output.
*   **Extensibility:** New agents (e.g., an Insider Trading Analyst or Options Flow Analyst) can be easily added to the parallel pipeline in the future without rewriting the core logic.

### Negative Impacts (Cons / Risks)
*   **Increased Complexity:** Managing three LLM calls per request is inherently more complex than managing one.
*   **Compounded Failure Rates:** More network calls to the LLM provider increase the statistical likelihood of a timeout or `502 Bad Gateway` error.

## 5. Mitigation Strategies
To address the risks introduced by this decision, the following mitigations are required in the implementation:
1.  **Strict Timeout Budgets:** Hard timeouts will be enforced at the code level (1.5s for data, 2.5s for sub-agents, 3.0s for the Orchestrator).
2.  **Aggressive Caching:** A 15-minute TTL cache will be implemented for the `/api/v1/analysis/{ticker}` endpoint. This ensures that repeated requests for popular tickers (e.g., AAPL, TSLA) bypass the multi-agent workflow entirely, dropping latency to ~50ms and reducing API costs to $0.00.