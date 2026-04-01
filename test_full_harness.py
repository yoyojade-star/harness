import os
import sys
from google import genai
from google.genai import types
import personas  # Ensure personas.py is in the same folder

# --- CONFIGURATION ---
# Gemini 2.0 Flash is recommended for speed/cost during iterations.
# Gemini 2.0 Pro is recommended for the Architect/Evaluator roles if logic is complex.
# Uses GEMINI_API_KEY or GOOGLE_API_KEY from the environment (same as test_harness.py).
client = genai.Client()
MODEL_ID = "gemini-3.1-pro-preview" 

class EngineeringHarness:
    def __init__(self):
        self.state = {
            "prd": "", "arch": "", "ard": "", 
            "be_code": "", "fe_code": "", 
            "be_test": "", "fe_test": ""
        }
        self.max_retries = 5

    def call_agent(self, instruction, user_input):
        """The core execution engine for each persona."""
        response = client.models.generate_content(
            model=MODEL_ID,
            config=types.GenerateContentConfig(
                system_instruction=instruction,
                temperature=0.1, # Keep it low for precise engineering
            ),
            contents=user_input
        )
        return response.text

    def run_workflow(self, idea):
        # 1. Product Discovery
        print("[Step 1] Generating Product Spec...")
        self.state["prd"] = self.call_agent(personas.PO_INSTRUCTIONS, idea)

        # 2. Architecture & Human-in-the-loop
        print("[Step 2] Designing Architecture...")
        self.state["arch"] = self.architecture_loop()

        # 3. Implementation & Validation Loops
        print("[Step 3] Implementing Backend & Frontend...")
        self.state["be_code"] = self.iterative_loop("Backend", personas.BACKEND_ENGINEER_INSTRUCTIONS)
        self.state["fe_code"] = self.iterative_loop("Frontend", personas.FRONTEND_ENGINEER_INSTRUCTIONS)

        # 4. Final Testing
        print("[Step 4] Generating Test Suites...")
        self.state["be_test"] = self.call_agent(personas.TEST_ENGINEER_INSTRUCTIONS, self.state["be_code"])
        self.state["fe_test"] = self.call_agent(personas.TEST_ENGINEER_INSTRUCTIONS, self.state["fe_code"])

        self.save_output()

    def architecture_loop(self):
        """Loop for human approval and ARD generation."""
        current_design = self.call_agent(personas.ARCHITECT_INSTRUCTIONS, self.state["prd"])
        history = []
        while True:
            print(f"\n--- PROPOSED DESIGN ---\n{current_design}\n")
            feedback = input("[Human]: Type 'approve' or provide feedback: ")
            if feedback.lower() == "approve":
                ard = self.call_agent(personas.ARD_GENERATOR_INSTRUCTIONS, f"Design: {current_design}\nHistory: {history}")
                self.state["ard"] = ard
                return current_design
            history.append(feedback)
            current_design = self.call_agent(personas.ARCHITECT_REFINEMENT_INSTRUCTIONS, f"Prev: {current_design}\nFeedback: {feedback}")

    def iterative_loop(self, label, eng_instr):
        """The 5-iteration quality gate."""
        context = f"PRD: {self.state['prd']}\nARD: {self.state['ard']}\nARCH: {self.state['arch']}"
        code = self.call_agent(eng_instr, context)
        
        for i in range(1, self.max_retries + 1):
            print(f"   [{label}] Iteration {i} checking...")
            eval_report = self.call_agent(personas.EVALUATOR_INSTRUCTIONS, f"CONTEXT: {context}\nCODE: {code}")
            sec_report = self.call_agent(personas.SECURITY_AUDITOR_INSTRUCTIONS, f"CODE: {code}")

            if "[PASS]" in eval_report and "[SEC-PASS]" in sec_report:
                print(f"   [OK] {label} Approved.")
                return code
            
            print(f"   [FAIL] {label} issues found. Repairing...")
            code = self.call_agent(eng_instr, f"CONTEXT: {context}\nERRORS: {eval_report}\nSEC_ERRORS: {sec_report}\nCODE: {code}")
        
        return code

    def save_output(self):
        os.makedirs("output/tests", exist_ok=True)
        files = {
            "output/PRD.md": self.state["prd"],
            "output/ARCH.md": self.state["arch"],
            "output/ARD.md": self.state["ard"],
            "output/backend.py": self.state["be_code"],
            "output/frontend.tsx": self.state["fe_code"],
            "output/tests/test_be.py": self.state["be_test"],
            "output/tests/test_fe.tsx": self.state["fe_test"],
        }
        for path, data in files.items():
            with open(path, "w", encoding="utf-8") as f:
                f.write(data)
        print("\n[DONE] All systems go. Check the /output folder.")

if __name__ == "__main__":
    harness = EngineeringHarness()
    harness.run_workflow("Live Auction Platform - where sellers can list items for auction and buyers can bid on them")