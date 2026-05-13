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
    entities: dict[str, Any]
    requires_tools: bool
    recommended_tools: list[str]
    plan: list[str]
    missing_info: list[str]
    safety_notes: list[str]


VALID_INTENTS = {
    "track_order",
    "refund_order",
    "log_complaint",
    "customer_profile",
    "general_question",
}

TOOLS_BY_INTENT = {
    "track_order": ["OrderLookupTool"],
    "refund_order": ["OrderLookupTool", "RefundTool"],
    "log_complaint": ["ComplaintLoggerTool"],
    "customer_profile": ["CustomerProfileTool"],
}

ALLOWED_TOOL_NAMES = {
    tool_name
    for tool_names in TOOLS_BY_INTENT.values()
    for tool_name in tool_names
}

TOOL_REQUIRED_INTENTS = set(TOOLS_BY_INTENT)


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


def coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def coerce_int_or_none(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# Build a safe fallback result if the LLM output is malformed
def fallback_result(user_text: str) -> PlannerResult:
    order_match = re.search(r"\b\d+\b", user_text)
    order_id = int(order_match.group()) if order_match else None
    lowered = user_text.lower()

    if "refund" in lowered:
        intent = "refund_order"
    elif "complain" in lowered or "complaint" in lowered:
        intent = "log_complaint"
    elif "profile" in lowered:
        intent = "customer_profile"
    elif "order" in lowered or "track" in lowered or "status" in lowered:
        intent = "track_order"
    else:
        intent = "general_question"

    return {
        "input": user_text,
        "intent": intent,
        "order_id": order_id,
        "product": None,
        "date": None,
        "entities": {
            "order_id": order_id,
            "product": None,
            "date": None,
        },
        "requires_tools": intent in TOOL_REQUIRED_INTENTS,
        "recommended_tools": TOOLS_BY_INTENT.get(intent, []),
        "plan": [
            "Use the extracted intent and entities as guidance.",
            "Call tools only when database-backed information or an update is required.",
            "Generate a concise customer-facing answer from tool observations.",
        ],
        "missing_info": ["order_id"] if intent in {"track_order", "refund_order"} and order_id is None else [],
        "safety_notes": [
            "Do not invent database facts.",
            "Do not claim an update succeeded unless the tool result confirms it.",
        ],
    }


def normalize_planner_result(user_text: str, parsed: dict[str, Any]) -> PlannerResult:
    entities = parsed.get("entities")
    if not isinstance(entities, dict):
        entities = {}

    intent = str(parsed.get("intent", "general_question"))
    if intent not in VALID_INTENTS:
        intent = "general_question"

    order_id = coerce_int_or_none(parsed.get("order_id", entities.get("order_id")))
    product = parsed.get("product", entities.get("product"))
    date = parsed.get("date", entities.get("date"))
    requires_tools = bool(parsed.get("requires_tools", intent in TOOL_REQUIRED_INTENTS))
    raw_recommended_tools = coerce_list(
        parsed.get("recommended_tools", TOOLS_BY_INTENT.get(intent, []))
    )
    recommended_tools = [
        tool_name
        for tool_name in raw_recommended_tools
        if tool_name in ALLOWED_TOOL_NAMES
    ]
    if intent in TOOLS_BY_INTENT and not recommended_tools:
        recommended_tools = TOOLS_BY_INTENT[intent]

    return {
        "input": user_text,
        "intent": intent,
        "order_id": order_id,
        "product": product,
        "date": date,
        "entities": {
            "order_id": order_id,
            "product": product,
            "date": date,
        },
        "requires_tools": requires_tools,
        "recommended_tools": recommended_tools,
        "plan": coerce_list(parsed.get("plan")),
        "missing_info": coerce_list(parsed.get("missing_info")),
        "safety_notes": coerce_list(parsed.get("safety_notes")),
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
4. Create high-level planning context for a downstream ReAct agent

Valid intents:
- track_order
- refund_order
- log_complaint
- customer_profile
- general_question

Return JSON only with this exact structure:
{
  "intent": "refund_order",
  "order_id": 1001,
  "product": null,
  "date": null,
  "entities": {
    "order_id": 1001,
    "product": null,
    "date": null
  },
  "requires_tools": true,
  "recommended_tools": ["OrderLookupTool", "RefundTool"],
  "plan": [
    "Verify that order 1001 exists.",
    "Request a refund if the order is valid.",
    "Generate a concise customer-facing response from tool observations."
  ],
  "missing_info": [],
  "safety_notes": [
    "Do not invent database facts.",
    "Do not claim an update succeeded unless the tool result confirms it."
  ]
}

Rules:
- Use null if no order id is present
- Use null if product is not mentioned
- Use null if date is not mentioned
- Keep the plan short and practical
- recommended_tools may include only these names:
  OrderLookupTool, CustomerProfileTool, RefundTool, ComplaintLoggerTool
- The planner gives guidance only. The downstream ReAct agent decides and executes tool calls.
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
        return normalize_planner_result(user_text, parsed)
    except Exception:
        return fallback_result(user_text)
