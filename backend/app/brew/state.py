from typing import TypedDict, List
from langchain_core.messages import BaseMessage


class BrewState(TypedDict):
    messages: List[BaseMessage]
