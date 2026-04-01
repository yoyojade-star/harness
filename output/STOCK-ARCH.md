Here is the updated Technical Design Document (TDD). 

### 📝 Summary of Changes Based on Feedback:
1.  **LLM Provider Changed:** Replaced OpenAI (`gpt-4o-mini`) with **Google Gemini** (`gemini-1.5-flash` for optimal speed/cost).
2.  **Architecture Shifted to Agentic Workflow:** Replaced the single-prompt approach with a **Multi-Agent Orchestration** model.
3.  **Personas Introduced:** Defined specific personas for three distinct agents: *Quantitative Analyst*, *News Sentiment Analyst*, and *Lead Portfolio Manager (Orchestrator)*.
4.  **Orchestration Pipeline Added:** Detailed a concurrent pipeline where data fetching and sub-agent processing happen in parallel before being synthesized by the Orchestrator Agent.
5.  **Code Snippets Updated:** Updated the AI integration code to reflect the `google-generativeai` SDK and Gemini's native JSON schema enforcement.
6.  **Timeouts Adjusted:** Recalculated the timeout budget in Section 7 to accommodate the multi-step agentic workflow while strictly maintaining the < 8-second latency requirement.

---

# 🛠️ Technical Design Document (TDD)
**Product:** StockSense AI (MVP)
**Document Version:** 1.1 (Updated with Agentic Architecture)
**Architect:** [Your Name], Lead Architect
**Date:** October 24, 2023

## 1. System Architecture Overview
The system follows a modern, decoupled Client-Server architecture. The backend acts as a stateless orchestration layer (BFF - Backend for Frontend) utilizing an **Agentic AI Workflow**. 

To meet the strict **< 8-second latency** requirement, the system will utilize **Asynchronous I/O** to fetch data and process sub-agent tasks concurrently, before a final Orchestrator Agent synthesizes the output.

### 1.1. Technology Stack Decisions
*   **Frontend:** Next.js (React) + Tailwind CSS.
*   **Backend:** Python 3.11 + FastAPI. *Justification: Native `async/await` support is critical for orchestrating multiple AI agents concurrently.*
*   **Market API:** Alpha Vantage.
*   **News API:** Finnhub.
*   **LLM / AI Framework:** **Google Gemini (`gemini-1.5-flash`)**. *Justification: Gemini 1.5 Flash offers massive context windows, native JSON structuring, and lightning-fast inference speeds required for a multi-agent workflow within an 8-second budget.*

---

## 2. Data Flow & Agent Orchestration Sequence
To achieve the latency requirement, external data fetching and sub-agent processing are pipelined and parallelized.

1.  **Client** sends `GET /api/v1/analysis/{ticker}`.
2.  **FastAPI** validates the ticker format.
3.  **FastAPI** initiates two concurrent asynchronous pipelines (`asyncio.gather`):
    *   **Pipeline A (Quant):** Fetch Market Data $\rightarrow$ Pass to **Quantitative Analyst Agent**.
    *   **Pipeline B (News):** Fetch News Data $\rightarrow$ Pass to **News Sentiment Agent**.
4.  **FastAPI** collects the outputs from Pipeline A and Pipeline B.
5.  **FastAPI** passes both analyses to the **Lead Orchestrator Agent** (using Gemini's JSON mode) to make the final decision.
6.  **FastAPI** parses the Orchestrator's response, merges it with the raw Market Data, and returns the final payload to the Client.

---

## 3. API Specifications

### 3.1. Endpoint: Get Stock Analysis
*   **Path:** `/api/v1/analysis/{ticker}`
*   **Method:** `GET`

#### Success Response (200 OK)
```json
{
  "meta": {
    "ticker": "AAPL",
    "timestamp": "2023-10-24T14:30:00Z",
    "processing_time_ms": 5120
  },
  "market_data": {
    "current_price": 173.50,
    "currency": "USD",
    "previous_close": 171.10,
    "volume": 54200100,
    "percent_change": 1.40
  },
  "analysis": {
    "recommendation": "Buy",
    "confidence_score": 82,
    "reasoning": [
      "Quant Agent notes strong price action breaking above previous close on high volume.",
      "News Agent reports highly bullish sentiment following recent Asian market expansion.",
      "Overall alignment between technicals and fundamentals presents a strong buying opportunity."
    ],
    "data_sources_used": ["market_data", "news_data"]
  }
}
```

---

## 4. Internal Data Schemas (Pydantic Models)

```python
from pydantic import BaseModel, Field
from typing import List, Literal

class MarketData(BaseModel):
    current_price: float
    currency: str = "USD"
    previous_close: float
    volume: int
    percent_change: float

# Schema used to enforce Gemini's Orchestrator JSON output
class AIAnalysis(BaseModel):
    recommendation: Literal["Buy", "Hold", "Sell"]
    confidence_score: int = Field(..., ge=0, le=100)
    reasoning: List[str] = Field(..., min_items=1, max_items=3)
    
class AnalysisResponse(BaseModel):
    meta: dict
    market_data: MarketData
    analysis: AIAnalysis
```

---

## 5. Agentic Architecture & Orchestration Strategy

Instead of a single prompt, we utilize three distinct Gemini agents with specific personas. This separation of concerns improves reasoning quality and reduces hallucinations.

### 5.1. Agent Personas & Prompts

**Agent 1: Quantitative Analyst**
*   **Persona:** *"You are a strict, data-driven Quantitative Financial Analyst. You only care about numbers, price action, and volume."*
*   **Task:** Analyze the raw market data JSON. Output a 2-sentence technical summary and a technical sentiment score (Bullish/Bearish/Neutral).

**Agent 2: News Sentiment Analyst**
*   **Persona:** *"You are a sharp, perceptive Financial Journalist and Sentiment Analyst. You excel at reading between the lines of news headlines."*
*   **Task:** Analyze the provided news headlines and summaries. Output a 2-sentence fundamental summary and a news sentiment score (Positive/Negative/Mixed).

**Agent 3: Lead Portfolio Manager (Orchestrator)**
*   **Persona:** *"You are the Lead Portfolio Manager at a top-tier hedge fund. You synthesize reports from your Quant and News analysts to make final trading decisions."*
*   **Task:** Review the outputs from the Quant Analyst and News Analyst. Make a final recommendation. You MUST output strictly in the provided JSON schema.

### 5.2. Gemini API Orchestration Implementation
```python
import google.generativeai as genai
import asyncio

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

async def run_quant_agent(market_data):
    prompt = f"Persona: Strict Quant Analyst. Analyze this data: {market_data}"
    response = await model.generate_content_async(prompt)
    return response.text

async def run_news_agent(news_data):
    prompt = f"Persona: Financial Sentiment Analyst. Analyze this news: {news_data}"
    response = await model.generate_content_async(prompt)
    return response.text

async def run_orchestrator(quant_report, news_report):
    prompt = f"""
    Persona: Lead Portfolio Manager.
    Quant Report: {quant_report}
    News Report: {news_report}
    Provide final recommendation.
    """
    # Enforce JSON output matching the Pydantic schema
    response = await model.generate_content_async(
        prompt,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=AIAnalysis # Passes the Pydantic model directly
        )
    )
    return response.text
```

---

## 6. Error Handling & Edge Cases

| Scenario | System Behavior | Frontend UX |
| :--- | :--- | :--- |
| **News API / News Agent Fails** | Backend catches error, passes a "No news data available" string to the Orchestrator. Orchestrator relies solely on Quant report. | Displays analysis, but adds a warning icon: *"Analysis based on technicals only. News sentiment unavailable."* |
| **Orchestrator Agent times out** | Backend aborts Gemini call, returns `502 Bad Gateway`. | Displays Market Data (Price) but shows an error in the AI section: *"AI Orchestrator currently overloaded. Please try again."* |
| **Invalid Ticker Input** | FastAPI regex validation fails immediately (0ms latency). Returns `400`. | Search bar turns red: *"Please enter a valid ticker symbol."* |

---

## 7. Performance & Cost Optimization (Meeting KPIs)

To ensure the multi-agent workflow does not breach the 8-second latency limit, strict timeout budgets are enforced:

1.  **Latency Budgeting:**
    *   Data Fetching (Parallel): Max 1.5 seconds.
    *   Sub-Agents (Quant & News, Parallel): Max 2.5 seconds.
    *   Orchestrator Agent: Max 3.0 seconds.
    *   **Total Max Execution Time:** ~7.0 seconds.
2.  **Caching Layer (Crucial for Latency & Cost):**
    *   Implement an in-memory cache (e.g., Python's `cachetools` or Redis) for the `/api/v1/analysis/{ticker}` endpoint.
    *   **TTL (Time to Live):** 15 minutes.
    *   *Why?* Bypasses the entire agentic workflow for repeated queries, dropping latency to ~50ms and saving Gemini API tokens.
3.  **Model Selection:**
    *   Using `gemini-1.5-flash` instead of `gemini-1.5-pro` is a deliberate architectural choice to prioritize the < 8s latency requirement and keep costs well under the $0.02/query KPI.

---

## 8. Security & Compliance
*   **API Keys:** All external API keys (Google AI Studio / Vertex AI, Finnhub, Alpha Vantage) will be stored in environment variables (`.env`) and never exposed to the frontend.
*   **Rate Limiting:** Implement a basic rate limiter on the FastAPI backend (e.g., `slowapi`) restricting users (by IP) to 10 requests per minute.
*   **Disclaimer Enforcement:** The Frontend architecture must include a hardcoded, non-removable footer component stating: *"StockSense AI provides informational analysis only and does not constitute financial advice."*