from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph , START , END
from typing import TypedDict
import os
import dotenv
from planner import planner_node


# Load environment variables from .env
dotenv.load_dotenv()

# Define which LLM model to use
MODEL = "gpt-4o"

# Read the user's question from the terminal
user_input = input("Please enter your query: ")

# Create the LLM client
llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_KEY"),
    base_url=os.getenv("OPENAI_BASE"),
    model=MODEL
)

# Define the shared state used across the workflow
class AgentState(TypedDict):
    input:str
    intent:str
    order_id:int | None
    product:str | None
    date:str | None
    plan:str
    tool_result:str
    final_answer:str
    verified:bool

# Planner node is now imported from planner.py

# Tool node: simulate tool execution or external actions
def tool_node(state:AgentState):
    prompt = f""
    tool_result = llm.invoke(prompt).content
    return {"tool_result":tool_result}

# Verifier node: check whether the result is acceptable
def verifier_node(state:AgentState):
    prompt = f""
    verification = llm.invoke(prompt).content
    return {"verified":verification == "yes"}

def main():
    # Build the LangGraph workflow
    builder = StateGraph(AgentState)
    builder.add_node("planner", planner_node)
    builder.add_edge(START, "planner")
    builder.add_edge("planner", END)

    # Keep these nodes for the next workflow steps
    # builder.add_node("tool", tool_node)
    # builder.add_node("verifier", verifier_node)
    # builder.add_edge("planner", "tool")
    # builder.add_edge("tool", "verifier")
    # builder.add_edge("verifier", END)

    # Compile and run the planner-only workflow
    graph = builder.compile()
    result = graph.invoke({"input": user_input})

    # Print the planner output for quick testing
    print("Planner output:")
    print(result)

    # Temporary direct LLM call for basic response testing
    # response = llm.invoke([
    #     ("system", "You are a helpful assistant."),
    #     ("human", user_input)
    # ])
    # print(response.content)


if __name__ == "__main__":
    main()
