import json
import os
import dotenv
import readline
from typing import Annotated, Any, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from ltm import (
    extract_customer_id_from_messages,
    get_current_customer_id,
    get_latest_memory_value,
    write_customer_memory,
)
from planner import planner_node
from stm import create_checkpointer, create_session_config, create_session_id
from tools import CUSTOMER_SERVICE_TOOLS
from verifier import verifier as verify_tool_output


# Load environment variables from .env
dotenv.load_dotenv()

# Define which LLM model to use
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
MAX_TOOL_ITERATIONS = int(os.getenv("MAX_TOOL_ITERATIONS", "4"))
MAX_RESPONSE_REVISIONS = int(os.getenv("MAX_RESPONSE_REVISIONS", "2"))

# Create the LLM client and bind tools for ReAct tool calling.
base_llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_KEY"),
    base_url=os.getenv("OPENAI_BASE"),
    model=MODEL,
    temperature=0,
)
llm = base_llm.bind_tools(CUSTOMER_SERVICE_TOOLS)


# Define the shared state used across the workflow
class AgentState(TypedDict):
    input: str
    planner_result: dict[str, Any]
    messages: Annotated[list, add_messages]
    ltm_write: dict[str, Any]
    tool_iterations: int
    response_revisions: int
    verification_target: str
    response_verification: str


SYSTEM_PROMPT = """
You are an intelligent customer service ReAct agent.

Use the planner result as guidance, but use tool results as the source of truth.
Use tools for order status, customer profile, refund requests, and complaints.
Use earlier messages in the same session when the user refers to previous context.
Use long-term memory context from the planner result when available.
Do not invent database facts.
If a tool returns an error, explain it clearly.
Keep the final response concise and customer-friendly.
""".strip()


def build_ltm_summary(planner_result: dict[str, Any]) -> str:
    ltm_context = planner_result.get("ltm") if isinstance(planner_result, dict) else None
    if not isinstance(ltm_context, dict) or not ltm_context.get("ok"):
        return "none"

    memories = ltm_context.get("memories") or []
    lines: list[str] = []

    for memory in memories:
        key = memory.get("key") if isinstance(memory, dict) else None
        value = memory.get("value") if isinstance(memory, dict) else None
        if key is None and value is None:
            continue
        if key is None:
            line = str(value)
        else:
            line = f"{key}: {value}"
        lines.append(f"- {line}")

    return "\n".join(lines) if lines else "none"


# Planner node: extract intent and prepare structured guidance.
def planner(state: AgentState):
    result = planner_node(
        {
            "input": state["input"],
            "messages": state.get("messages", []),
        }
    )
    return {
        "planner_result": result,
        "tool_iterations": 0,
        "response_revisions": 0,
        "verification_target": "",
        "response_verification": "",
    }


# ReAct node: read planner output plus chat history, then decide on tool use.
def react(state: AgentState):
    planner_context = json.dumps(
        state.get("planner_result", {}),
        indent=2,
        ensure_ascii=False,
    )
    ltm_summary = build_ltm_summary(state.get("planner_result", {}))
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        SystemMessage(
            content=(
                "Long-term memory summary:\n"
                f"{ltm_summary}\n"
                "If the verifier asked for a response revision, fix the issue and return "
                "a corrected customer-facing response.\n"
                "If a tool is needed, call it. If enough verified information is available, "
                "return the final customer-facing response."
            )
        ),
        SystemMessage(content=f"Planner result:\n{planner_context}"),
        *state["messages"],
    ]
    response = llm.invoke(messages)
    return {"messages": [response]}


def verifier(state: AgentState):
    result = verify_tool_output(state)
    if result.get("verification_target") != "tool":
        response_verification = str(result.get("response_verification", ""))
        if response_verification.lstrip().upper().startswith("ISSUE:"):
            return {
                **result,
                "response_revisions": int(state.get("response_revisions") or 0) + 1,
            }
        return result

    return {
        **result,
        "tool_iterations": int(state.get("tool_iterations") or 0) + 1,
    }


def route_after_react(state: AgentState):
    messages = state.get("messages", [])
    if not messages:
        return "ltm_write"

    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "tools"
    return "verifier"


def route_after_verifier(state: AgentState):
    if state.get("verification_target") == "response":
        response_verification = str(state.get("response_verification", ""))
        is_issue = response_verification.lstrip().upper().startswith("ISSUE:")
        if is_issue and int(state.get("response_revisions") or 0) < MAX_RESPONSE_REVISIONS:
            return "react"
        return "ltm_write"

    if int(state.get("tool_iterations") or 0) >= MAX_TOOL_ITERATIONS:
        return "ltm_write"

    return "react"


def ltm_write(state: AgentState):
    planner_result = state.get("planner_result", {}) or {}
    ltm_context = planner_result.get("ltm")
    user_text = str(state.get("input", "")).strip()
    intent = planner_result.get("intent")
    order_id = planner_result.get("order_id")

    customer_id = planner_result.get("customer_id")
    if isinstance(ltm_context, dict) and ltm_context.get("ok"):
        customer_id = ltm_context.get("customer_id")

    if customer_id is None:
        customer_id = extract_customer_id_from_messages(state.get("messages", []))

    if customer_id is None:
        customer_id = get_current_customer_id()

    updates: list[tuple[str, str]] = []
    lower_text = user_text.lower()

    if "remember" in lower_text and "refund" in lower_text:
        updates.append(("refund_preference", "refund"))

    if intent == "refund_order":
        updates.append(("refund_preference", "refund"))
        if order_id is not None:
            updates.append(("last_refund_order", str(order_id)))

    if intent == "log_complaint":
        issue_summary = user_text[:200]
        if issue_summary:
            updates.append(("last_issue_summary", issue_summary))

    if "late" in lower_text:
        memories = []
        if isinstance(ltm_context, dict):
            memories = ltm_context.get("memories", []) or []
        latest_count = get_latest_memory_value(memories, "late_delivery_count")
        count = int(latest_count) if latest_count and latest_count.isdigit() else 0
        updates.append(("late_delivery_count", str(count + 1)))
        updates.append(("last_issue_summary", "late_delivery"))

    if not updates:
        return {
            "ltm_write": {
                "ok": True,
                "reason": "no_updates",
                "writes": [],
            }
        }

    if customer_id is None:
        return {
            "ltm_write": {
                "ok": False,
                "reason": "missing_customer_id",
                "writes": [],
            }
        }

    writes = []
    for key, value in updates:
        writes.append(
            write_customer_memory(
                customer_id=int(customer_id),
                key=key,
                value=value,
            )
        )

    return {
        "ltm_write": {
            "ok": True,
            "customer_id": int(customer_id),
            "writes": writes,
        }
    }


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("planner", planner)
    builder.add_node("react", react)
    builder.add_node("tools", ToolNode(CUSTOMER_SERVICE_TOOLS))
    builder.add_node("verifier", verifier)
    builder.add_node("ltm_write", ltm_write)
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "react")
    builder.add_conditional_edges(
        "react",
        route_after_react,
        {"tools": "tools", "verifier": "verifier"},
    )
    builder.add_edge("tools", "verifier")
    builder.add_conditional_edges(
        "verifier",
        route_after_verifier,
        {"react": "react", "ltm_write": "ltm_write"},
    )
    builder.add_edge("ltm_write", END)

    return builder.compile(checkpointer=create_checkpointer())


def main():
    graph = build_graph()
    session_id = create_session_id()
    session_config = create_session_config(session_id)

    print(f"STM session started: {session_id}")
    print("Type 'exit' to quit.")

    while True:
        user_input = input("Please enter your query: ").strip()

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit"}:
            break

        # Invoke the graph with the same session config to keep STM.
        result = graph.invoke(
            {
                "input": user_input,
                "messages": [HumanMessage(content=user_input)],
            },
            config=session_config,
        )

        print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
