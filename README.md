# Codex Guardian
AI-assisted incident response with human-in-the-loop oversight.

## Pipeline
Alert → Context Ingestion → Risk Scoring → [Gate 1: Validate Diagnosis] → Patch Generation → [Gate 2: Approve Fix] → Sandbox → Deploy → Audit Log

## Setup
1. Copy `.env.example` to `.env` and add your API key
2. `pip install -r requirements.txt`
3. `python main.py`
