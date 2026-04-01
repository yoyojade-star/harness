import os
import json
import requests
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# ---------------------------------------------------------
# 1. Define the Expected Output Schema
# ---------------------------------------------------------
class TicketRoutingDecision(BaseModel):
    is_machine_solvable: bool = Field(
        description="Set to True ONLY if the ticket can be resolved automatically with 100% certainty. Otherwise, False."
    )
    confidence_score: float = Field(
        description="A float between 0.0 and 1.0 representing confidence in the decision."
    )
    reasoning: str = Field(
        description="A brief, 1-2 sentence explanation of why this routing decision was made."
    )

# ---------------------------------------------------------
# 2. Integration Mocks (Jira & PagerDuty)
# ---------------------------------------------------------
def fetch_jira_ticket(ticket_id: str) -> dict:
    """Mock function to simulate fetching a Jira ticket."""
    # In production, use the 'jira' python library or REST API
    return {
        "id": ticket_id,
        "title": "Database connection pool exhausted on production-db-01",
        "description": "Getting multiple connection timeout errors from the backend services trying to reach the primary PostgreSQL database.",
        "component": "Database",
        "priority": "High"
    }

def trigger_pagerduty_incident(ticket_data: dict, routing_reasoning: str):
    """Triggers a PagerDuty incident using their Events API v2."""
    pd_routing_key = os.environ.get("PAGERDUTY_ROUTING_KEY", "your_dummy_key")
    
    payload = {
        "routing_key": pd_routing_key,
        "event_action": "trigger",
        "payload": {
            "summary": f"Human Intervention Required: {ticket_data['title']}",
            "source": "Gemini-Jira-Router",
            "severity": "critical",
            "custom_details": {
                "jira_ticket_id": ticket_data['id'],
                "ai_reasoning": routing_reasoning,
                "jira_description": ticket_data['description']
            }
        }
    }
    
    # Example POST request (commented out to prevent accidental firing)
    # response = requests.post("https://events.pagerduty.com/v2/enqueue", json=payload)
    # response.raise_for_status()
    print(f"🚨 [PAGERDUTY TRIGGERED] Incident created for Ticket {ticket_data['id']}.")
    print(f"   Reasoning: {routing_reasoning}\n")

def trigger_machine_automation(ticket_data: dict):
    """Mock function for triggering your automated remediation scripts."""
    print(f"🤖 [AUTOMATION TRIGGERED] Machine is resolving Ticket {ticket_data['id']}...\n")

# ---------------------------------------------------------
# 3. Core Routing Logic
# ---------------------------------------------------------
def process_ticket(ticket_id: str):
    # Initialize the Gemini client
    # It automatically picks up the GEMINI_API_KEY environment variable
    client = genai.Client()
    
    # 1. Fetch Ticket Data
    ticket = fetch_jira_ticket(ticket_id)
    
    # 2. Construct Prompt
    prompt = f"""
    You are a Level 1 Site Reliability Engineer (SRE) routing system.
    Analyze the following Jira ticket and determine if it can be resolved by automated machine scripts.
    
    Rules:
    - You must be 100% confident to mark 'is_machine_solvable' as True.
    - If there is ANY ambiguity, risk of data loss, or unknown variables, it requires a human.
    
    Ticket Details:
    Title: {ticket['title']}
    Component: {ticket['component']}
    Priority: {ticket['priority']}
    Description: {ticket['description']}
    """

    # 3. Call Gemini with Structured Outputs
    print(f"Analyzing ticket {ticket_id} with Gemini...")
    response = client.models.generate_content(
        model='gemini-2.5-pro', # Use pro for complex reasoning, flash for speed
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TicketRoutingDecision,
            temperature=0.0, # Use 0.0 for deterministic, factual routing
        ),
    )

    # 4. Parse the strict JSON response
    decision_data = json.loads(response.text)
    decision = TicketRoutingDecision(**decision_data)
    
    print(f"--- Gemini Decision ---")
    print(f"Machine Solvable: {decision.is_machine_solvable}")
    print(f"Confidence:       {decision.confidence_score}")
    print(f"Reasoning:        {decision.reasoning}")
    print(f"-----------------------\n")

    # 5. Route Based on strict thresholds
    # We double-check the confidence score programmatically as a safeguard
    if decision.is_machine_solvable and decision.confidence_score >= 0.99:
        trigger_machine_automation(ticket)
    else:
        trigger_pagerduty_incident(ticket, decision.reasoning)

# ---------------------------------------------------------
# Execution
# ---------------------------------------------------------
if __name__ == "__main__":
    # Ensure you have your API key set in your terminal:
    # export GEMINI_API_KEY="your_api_key_here"
    
    # Test the script
    if not os.environ.get("GEMINI_API_KEY"):
        print("⚠️ Please set your GEMINI_API_KEY environment variable.")
    else:
        process_ticket("ENG-4042")