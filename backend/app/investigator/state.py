from typing import TypedDict, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    topic: str
    research_plan: Dict[str, Any]  # The structured plan
    user_feedback: str  # Feedback provided by user at interrupt
    gathered_data: List[str]  # Accumulated findings
    final_report: str  # The markdown report
    messages: List[BaseMessage]  # Chat history for context
    model_name: Optional[str]  # Store model name for resuming
    thinking_enabled: Optional[bool]  # Store thinking flag for resuming
