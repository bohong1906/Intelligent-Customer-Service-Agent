from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph , START , END
from typing import TypedDict
import os
import dotenv


dotenv.load_dotenv()

MODEL = "gpt-4o"

user_input = input("Please enter your query: ")
llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_KEY"),
    base_url=os.getenv("OPENAI_BASE"),
    model=MODEL
)

class AgentState(TypedDict):
    input:str
    plan:str
    tool_result:str
    final_answer:str
    verified:bool

def planner_node(state:AgentState):
    prompt = f""
    plan = llm.invoke(prompt).content
    return {"plan":plan}

def tool_node(state:AgentState):
    prompt = f""
    tool_result = llm.invoke(prompt).content
    return {"tool_result":tool_result}

def verifier_node(state:AgentState):
    prompt = f""
    verification = llm.invoke(prompt).content
    return {"verified":verification == "yes"}

def main():
    builder = StateGraph(AgentState)
    builder.add_node("planner", planner_node)
    builder.add_node("tool", tool_node)
    builder.add_node("verifier", verifier_node)
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "tool")
    builder.add_edge("tool", "verifier")
    builder.add_edge("verifier", END)

    response = llm.invoke([
        ("system", "You are a helpful assistant."),
        ("human", user_input)
    ])
    print(response.content)


if __name__ == "__main__":
    main()