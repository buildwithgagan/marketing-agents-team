from typing import Dict, Any


def get_model_config(
    thread_id: str, model_name: str, thinking_enabled: bool, mode: str
) -> Dict[str, Any]:
    """
    Generates the 'configurable' dictionary for LangGraph/LangChain models
    based on the requested model and thinking settings.
    """
    config = {
        "configurable": {
            "thread_id": thread_id,
            "model_name": model_name,
            "mode": mode,
        }
    }

    # Thinking/Reasoning Logic
    if model_name.startswith("gpt-5") and thinking_enabled:
        config["configurable"]["reasoning"] = {"effort": "high", "summary": "auto"}
        config["configurable"]["output_version"] = "responses/v1"
    elif model_name.startswith("gpt-5"):
        # GPT-5 with thinking DISABLED -> Low effort, but still v1 API usually
        config["configurable"]["reasoning"] = {"effort": "low"}
        config["configurable"]["output_version"] = "responses/v1"

    # o1/o3: rely on model defaults; do not pass unsupported reasoning_effort

    return config
