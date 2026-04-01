# Harness

Python experiments that drive **Google Gemini** through multi-step “persona” workflows to go from a product idea to generated artifacts (specs, architecture, code, tests).

## Contents

| Script | Purpose |
|--------|---------|
| `test_full_harness.py` | Full pipeline: PRD → human-in-the-loop architecture → backend/frontend with QA + security gates → test suites. Writes everything under `output/`. |
| `test_harness.py` | Lighter loop: planner → generator (JSON file tree) → evaluator, saved under `my_generated_app/`. |
| `personas.py` | System-instruction strings for each role (PO, architect, engineers, evaluator, security, SDET). |

## Requirements

- Python 3.10+ (3.14 works with the current venv layout)
- A [Gemini API](https://ai.google.dev/) key

## Setup

```powershell
cd c:\src\pyproject\harness
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install google-genai
```

Set your API key (the client reads **`GEMINI_API_KEY`** or **`GOOGLE_API_KEY`**):

```powershell
$env:GEMINI_API_KEY = "your-key-here"
```

## Run

**Full harness** (you will be prompted at the architecture step; type `approve` or feedback):

```powershell
python test_full_harness.py
```

Edit the idea string at the bottom of `test_full_harness.py`, or import `EngineeringHarness` and call `run_workflow("your idea")`.

**Planner / generator harness:**

```powershell
python test_harness.py
```

## Configuration

In `test_full_harness.py`, set `MODEL_ID` to the Gemini model you want (for example a Flash model for speed or a Pro model for harder reasoning).

## Output (`test_full_harness.py`)

After a successful run:

| Path | Description |
|------|-------------|
| `output/PRD.md` | Product requirements |
| `output/ARCH.md` | Architecture / TDD-style design |
| `output/ARD.md` | Architecture decision record |
| `output/backend.py` | Generated backend (intended as FastAPI-style) |
| `output/frontend.tsx` | Generated frontend (React / TypeScript) |
| `output/tests/test_be.py` | Backend tests (PyTest-oriented) |
| `output/tests/test_fe.tsx` | Frontend tests (Vitest-oriented) |

Generated files are written as **UTF-8** so Unicode from the model is preserved on Windows.

## Notes

- **Secrets:** Do not commit API keys. Use environment variables only.
- **Git:** Consider ignoring `venv/`, `__pycache__/`, and optionally `output/` if those files are disposable.
