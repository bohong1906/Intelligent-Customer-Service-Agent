from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver


# Create the in-memory STM backend for one running session.
def create_checkpointer() -> MemorySaver:
    """Create an in-memory LangGraph checkpointer for short-term memory."""
    return MemorySaver()


# Generate a unique session id so repeated turns share the same STM thread.
def create_session_id() -> str:
    """Generate a unique session id for one chat session."""
    return f"customer-service-session-{uuid4().hex[:8]}"


# Build the config object used by LangGraph to reuse STM across turns.
def create_session_config(session_id: str) -> dict[str, Any]:
    """Build the LangGraph config used to reuse the same STM thread."""
    return {"configurable": {"thread_id": session_id}}
