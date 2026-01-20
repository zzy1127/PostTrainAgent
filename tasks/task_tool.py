from tasks.agent_types import AGENT_TYPES, get_agent_descriptions


TASK_TOOL = {
    "type": "function",
    "function": {
        "name": "Task",
        "description": f"Spawn a subagent for a focused subtask.\n\nAgent types:\n{get_agent_descriptions()}",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Short task description (3-5 words)",
                },
                "prompt": {
                    "type": "string",
                    "description": "Detailed instructions for the subagent",
                },
                "agent_type": {
                    "type": "string",
                    "enum": list(AGENT_TYPES.keys()),
                },
            },
            "required": ["description", "prompt", "agent_type"],
        },
    },
}


__all__ = ["TASK_TOOL"]


