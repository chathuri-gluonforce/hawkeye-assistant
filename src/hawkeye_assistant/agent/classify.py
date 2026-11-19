import json

from hawkeye_assistant.config import RESULTS_FILE
from hawkeye_assistant.llm import ask
from hawkeye_assistant.memory import store as memory

LABELS = [
    "match_invoice",
    "unmatched_items",
    "upload_document",
    "amount_mismatch",
    "recon_status",
    "show_details",
    "audit_query",
    "other",
]

DEFAULT_PROMPT = "Classify the customer message intent."


def resolve_prompt(use_best_prompt: bool = True) -> str:
    if use_best_prompt:
        try:
            with open(RESULTS_FILE) as results_file:
                prompt = json.load(results_file).get("best_prompt")
            if isinstance(prompt, str):
                return prompt
        except FileNotFoundError:
            pass
    return DEFAULT_PROMPT


def classify(text, prompt, use_memory=True):
    lessons = memory.search(text) if use_memory else []
    notes = "\n".join(f"- {lesson}" for _, lesson in lessons) or "- none"
    full = (
        f"{prompt}\nLabels: {', '.join(LABELS)}\n"
        f"Lessons from past mistakes:\n{notes}\n"
        f"Message: {text}\nAnswer with one label only."
    )
    pred = ask(full).lower().strip()
    return pred, [item_id for item_id, _ in lessons]
