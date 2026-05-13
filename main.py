from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing import Annotated, Any, TypedDict
import json
import os
import dotenv
import readline
from planner import planner_node
from tools import CUSTOMER_SERVICE_TOOLS


# Load environment variables from .env
dotenv.load_dotenv()

# Define which LLM model to use
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# Create the LLM client and bind tools for ReAct tool calling
llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_KEY"),
    base_url=os.getenv("OPENAI_BASE"),
    model=MODEL,
    temperature=0,
).bind_tools(CUSTOMER_SERVICE_TOOLS)


# Define the shared state used across the workflow
class AgentState(TypedDict):
    input: str
    planner_result: dict[str, Any]
    messages: Annotated[list, add_messages]


SYSTEM_PROMPT = """
You are an intelligent customer service ReAct agent.

Use the planner result as guidance, but use tool results as the source of truth.
Use tools for order status, customer profile, refund requests, and complaints.
Do not invent database facts.
If a tool returns an error, explain it clearly.
Keep the final response concise and customer-friendly.
""".strip()


# Planner node: understand intent and create high-level execution guidance
def planner(state: AgentState):
    result = planner_node({"input": state["input"]})
    return {"planner_result": result}


# Agent node: reason with planner output and decide whether to call tools
def react(state: AgentState):
    planner_context = json.dumps(
        state.get("planner_result", {}),
        indent=2,
        ensure_ascii=False,
    )
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        SystemMessage(content=f"Planner result:\n{planner_context}"),
        *state["messages"],
    ]
    response = llm.invoke(messages)
    return {"messages": [response]}


def main():
    user_input = input("Please enter your query: ")

    # Build the LangGraph ReAct workflow
    builder = StateGraph(AgentState)
    builder.add_node("planner", planner)
    builder.add_node("react", react)
    builder.add_node("tools", ToolNode(CUSTOMER_SERVICE_TOOLS))
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "react")
    builder.add_conditional_edges(
        "react",
        tools_condition,
        {"tools": "tools", END: END},
    )
    builder.add_edge("tools", "react")

    graph = builder.compile()
    result = graph.invoke({
        "input": user_input,
        "messages": [HumanMessage(content=user_input)],
    })

    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
