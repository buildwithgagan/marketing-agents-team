from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ResearchTask(BaseModel):
    name: str = Field(description="The specific name of the research task")
    goal: str = Field(description="The specific goal/question this task resolves")
    tool_hint: str = Field(
        description="The tool to use: 'tavily_search', 'scrape_competitor_page', 'get_google_trends', or 'get_autocomplete_suggestions'"
    )

    # --- FIX: Make this Optional with a default empty dict ---
    tool_args: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments for the tool, e.g., {'url': '...', 'query': '...'}. Return empty dict if none.",
    )


class ResearchPlan(BaseModel):
    tasks: List[ResearchTask] = Field(description="List of executable research tasks")


class UserIntent(BaseModel):
    action: str = Field(
        description="The action to take based on user feedback. Must be 'approve' or 'update'."
    )
    feedback_summary: Optional[str] = Field(
        description="Summarized feedback for the planner if action is 'update'. None if 'approve'."
    )