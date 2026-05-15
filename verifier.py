import json
import os
from typing import Any

import dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, ToolMessage


dotenv.load_dotenv()

VERIFIER_MODEL = os.getenv("OPENAI_VERIFIER_MODEL", "gpt-4o")

verifier_llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_KEY"),
    base_url=os.getenv("OPENAI_BASE"),
    model=VERIFIER_MODEL,
    temperature=0,
)

VERIFIER_PROMPT = """
Tool: {tool_name}, Args: {args}
Result: {result}
Is this output correct? Reply OK: or ISSUE:
""".strip()

RESPONSE_VERIFIER_PROMPT = """
User input: {user_input}
Planner result: {planner_result}
Long-term memory write result: {ltm_write}
Assistant response: {response}

Does the assistant response follow the available tool and memory facts,
avoid invented database claims, and answer the user correctly? Reply OK: or ISSUE:
""".strip()


def verifier(state: dict[str, Any]) -> dict[str, Any]:
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None

    if isinstance(last_message, ToolMessage):
        return verify_tool_message(messages, last_message)

    if isinstance(last_message, AIMessage):
        return verify_response_message(state, last_message)

    return {"messages": [], "verification_target": "none"}


def verify_tool_message(
    messages: list[Any],
    tool_message: ToolMessage,
) -> dict[str, Any]:
    tool_name, tool_args = _get_tool_call_context(messages, tool_message)
    tool_result = _format_tool_result(tool_message.content)
    verdict = verify_tool_result(tool_name, tool_args, tool_result)
    return {
        "verification_target": "tool",
        "messages": [
            AIMessage(content=f"Verifier: {verdict}")
        ]
    }


def verify_response_message(
    state: dict[str, Any],
    response_message: AIMessage,
) -> dict[str, Any]:
    response_text = _format_message_content(response_message.content)
    prompt = RESPONSE_VERIFIER_PROMPT.format(
        user_input=str(state.get("input", "")),
        planner_result=json.dumps(
            state.get("planner_result", {}),
            ensure_ascii=False,
            indent=2,
        ),
        ltm_write=json.dumps(
            state.get("ltm_write", {}),
            ensure_ascii=False,
            indent=2,
        ),
        response=response_text,
    )
    verdict = verifier_llm.invoke(prompt).content
    return {
        "verification_target": "response",
        "response_verification": verdict,
    }


def verify_tool_result(tool_name: str, args: dict[str, Any], result: str) -> str:
    prompt = VERIFIER_PROMPT.format(
        tool_name=tool_name,
        args=json.dumps(args, ensure_ascii=False),
        result=result,
    )
    verdict = verifier_llm.invoke(prompt).content
    return f"{verdict}\n{result}"


def _get_last_tool_message(messages: list[Any]) -> ToolMessage | None:
    for message in reversed(messages):
        if isinstance(message, ToolMessage):
            return message
    return None


def _get_tool_call_context(
    messages: list[Any],
    tool_message: ToolMessage,
) -> tuple[str, dict[str, Any]]:
    tool_name = tool_message.name or "unknown"
    tool_args: dict[str, Any] = {}
    tool_call_id = tool_message.tool_call_id

    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue

        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            continue

        for call in tool_calls:
            call_name = _get_tool_call_value(call, "name")
            call_id = _get_tool_call_value(call, "id") or _get_tool_call_value(
                call,
                "tool_call_id",
            )
            call_args = _get_tool_call_value(call, "args") or {}

            if tool_call_id and call_id == tool_call_id:
                return call_name or tool_name, call_args

            if call_name == tool_name and not tool_call_id:
                return call_name, call_args

    return tool_name, tool_args


def _get_tool_call_value(call: Any, key: str) -> Any:
    if isinstance(call, dict):
        return call.get(key)
    return getattr(call, key, None)


def _format_tool_result(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, indent=2)


def _format_message_content(content: Any) -> str:
    if isinstance(content, list):
        return " ".join(str(item) for item in content)
    return str(content)
