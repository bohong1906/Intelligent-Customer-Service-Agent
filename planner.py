import json
import os
import re
from typing import Any, TypedDict

import dotenv
from langchain_openai import ChatOpenAI


# Load environment variables from .env
dotenv.load_dotenv()


class PlannerResult(TypedDict):
    input: str
    intent: str
    order_id: int | None
    product: str | None
    date: str | None
    plan: str


# Create the LLM used by the planner node
def get_planner_llm() -> ChatOpenAI:
    api_key = os.getenv("OPENAI_KEY")
    base_url = os.getenv("OPENAI_BASE")
    model = os.getenv("OPENAI_MODEL", "gpt-4o")

    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0,
    )


# Try to read the first JSON object from the LLM output
def parse_planner_output(raw_text: str) -> dict[str, Any]:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if match:
        return json.loads(match.group())

    raise ValueError("Planner output is not valid JSON.")


# Build a safe fallback result if the LLM output is malformed
def fallback_result(user_text: str) -> PlannerResult:
    order_match = re.search(r"\b\d+\b", user_text)
    order_id = int(order_match.group()) if order_match else None

    return {
        "input": user_text,
        "intent": "general_question",
        "order_id": order_id,
        "product": None,
        "date": None,
        "plan": (
            "1. Ask a clarifying question if needed. "
            "2. Use a tool only when the request needs structured data."
        ),
    }


# Main planner node for intent extraction and action planning
def planner_node(state: dict[str, Any]) -> PlannerResult:
    user_text = str(state.get("input", "")).strip()
    llm = get_planner_llm()

    # Tell the model to return only the planning result in JSON
    system_prompt = """
You are the Planner Node in an intelligent customer service workflow.

Your job is to:
1. Understand the user's request
2. Extract the intent
3. Extract the order_id if present
4. Create a short execution plan for the next node

Valid intents:
- track_order
- refund_order
- log_complaint
- customer_profile
- write_memory
- read_memory
- general_question

Return JSON only with this exact structure:
{
  "intent": "track_order",
  "order_id": 1001,
  "product": null,
  "date": null,
  "plan": "1. ... 2. ... 3. ..."
}

Rules:
- Use null if no order id is present
- Use null if product is not mentioned
- Use null if date is not mentioned
- Keep the plan short and practical
- Do not include markdown
- Do not include extra keys
""".strip()

    human_prompt = f"User input: {user_text}"

    try:
        response = llm.invoke(
            [
                ("system", system_prompt),
                ("human", human_prompt),
            ]
        )
        parsed = parse_planner_output(response.content)

        return {
            "input": user_text,
            "intent": str(parsed.get("intent", "general_question")),
            "order_id": parsed.get("order_id"),
            "product": parsed.get("product"),
            "date": parsed.get("date"),
            "plan": str(parsed.get("plan", "")),
        }
    except Exception:
        return fallback_result(user_text)
