import os
import json
import re
from google import genai
from google.genai import types

# Initialize the Gemini client (automatically picks up GEMINI_API_KEY from environment)
client = genai.Client()

# Configuration
MODEL_NAME = 'gemini-3.1-pro-preview' # Use Pro for complex coding tasks
PROJECT_DIR = './my_generated_app'
MAX_SPRINTS = 3

def clean_json_response(text):
    """Helper to strip markdown code blocks from LLM JSON output."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def run_planner(user_idea):
    print("🧠 [PLANNER] Drafting product specification...")
    system_prompt = """You are an expert Product Manager. Your job is to take a brief user idea and expand it into a comprehensive Product Specification. Focus ONLY on deliverables, core features, user stories, and the user experience. Do NOT specify granular technical details, coding languages, or architecture. Output the final specification in clean, highly structured Markdown."""
    
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_idea,
        config=types.GenerateContentConfig(system_instruction=system_prompt)
    )
    return response.text

def run_generator(spec, feedback=""):
    print("💻 [GENERATOR] Writing code...")
    system_prompt = """You are an expert Full-Stack Software Engineer. You have been provided with a Product Specification (and potentially feedback from QA). Your goal is to write the complete code for this application based on the spec.
    CRITICAL INSTRUCTION: You must output your final response ONLY as a valid JSON object where the keys are the file paths (e.g., 'index.html', 'script.js', 'style.css') and the values are the raw string content of those files. Do not wrap the JSON in markdown blocks."""
    
    prompt = f"PRODUCT SPECIFICATION:\n{spec}\n\n"
    if feedback:
        prompt += f"QA FEEDBACK TO FIX:\n{feedback}\n\n"
    prompt += "Generate the application code now as a JSON object."

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.2)
    )
    
    # Parse the JSON output
    try:
        clean_text = clean_json_response(response.text)
        files_dict = json.loads(clean_text)
        return files_dict
    except json.JSONDecodeError:
        print("⚠️ [ERROR] Generator failed to output valid JSON. Retrying...")
        return None

def run_evaluator(spec, files_dict):
    print("🕵️ [EVALUATOR] Reviewing code against spec...")
    system_prompt = """You are a ruthless, highly skeptical Quality Assurance Engineer. Review the provided codebase against the original Product Specification. You are grading on Feature Completeness, Logic, and Code Quality. 
    CRITICAL INSTRUCTION: Your response must start with exactly "PASS" or "FAIL" on the first line. If you FAIL the code, provide a detailed, itemized list of what is missing or broken on the subsequent lines."""
    
    # Combine the files into a readable format for the Evaluator
    codebase_text = "CODEBASE:\n"
    for filepath, content in files_dict.items():
        codebase_text += f"\n--- {filepath} ---\n{content}\n"

    prompt = f"PRODUCT SPECIFICATION:\n{spec}\n\n{codebase_text}\n\nEvaluate the code."

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.1)
    )
    return response.text

def save_project(files_dict, directory):
    """Saves the generated dictionary of files to the local file system."""
    os.makedirs(directory, exist_ok=True)
    for filepath, content in files_dict.items():
        # Handle subdirectories if the LLM generates them (e.g., 'src/app.js')
        full_path = os.path.join(directory, filepath)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
    print(f"📁 Project saved successfully to '{directory}/'")

# ==========================================
# THE HARNESS EXECUTION LOOP
# ==========================================
if __name__ == "__main__":
    print("🚀 Starting AI Harness...")
    user_idea = "I want to build one system for skier to upload their ski videos for analysis, the backend could process the videos, and generate feedback, and also returning the synthesized video for user to view. the skier should be able to chat with the system to have better understanding of the analysis, at the same time, they can track whether they make any progress based on the history data. "
    
    # Step 1: Planning
    spec = run_planner(user_idea)
    os.makedirs(PROJECT_DIR, exist_ok=True)
    with open(os.path.join(PROJECT_DIR, 'spec.md'), 'w') as f:
        f.write(spec)
    print("✅ Spec generated and saved.")

    # Step 2 & 3: The Generator-Evaluator Loop
    feedback = ""
    for iteration in range(1, MAX_SPRINTS + 1):
        print(f"\n--- Sprint {iteration}/{MAX_SPRINTS} ---")
        
        # Generator creates the files
        generated_files = run_generator(spec, feedback)
        
        if not generated_files:
            continue # Skip to next loop if JSON parsing failed

        # Save current state to disk
        save_project(generated_files, PROJECT_DIR)

        # Evaluator checks the files
        evaluation_result = run_evaluator(spec, generated_files)
        print(f"\nQA Report:\n{evaluation_result}\n")

        # Check loop condition
        if evaluation_result.strip().upper().startswith("PASS"):
            print("🎉 QA PASSED! Application is ready.")
            break
        else:
            print("❌ QA FAILED. Passing feedback back to Generator...")
            # Extract just the feedback text (removing the "FAIL" header)
            feedback = "\n".join(evaluation_result.split("\n")[1:])
            
    else:
        print("⚠️ Reached max iterations. Harness stopped.")