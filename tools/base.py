# tools/base.py
from tasks.agent_types import AGENT_TYPES
from skills.skill_tool import SKILL_TOOL
from tasks.task_tool import TASK_TOOL

# 将 wait 混入基础工具集
BASE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run shell command in the current environment. Use background=True for long-running tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to execute."},
                    "background": {
                        "type": "boolean",
                        "description": "If true, runs command in background (nohup) and returns PID.",
                        "default": False
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "limit": {"type": "integer", "description": "Max lines to read"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or append content to a file. Use this to create scripts or overwrite existing ones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "append": {
                        "type": "boolean",
                        "description": "If true, appends to file instead of overwriting.",
                        "default": False
                    }
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace exact text in a file. WARNING: 'old_text' must match the file content EXACTLY (including whitespace/newlines). If uncertain, use write_file to overwrite the whole file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "TodoWrite",
            "description": "Update task list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                },
                                "activeForm": {"type": "string"},
                            },
                            "required": ["content", "status", "activeForm"],
                        },
                    }
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Pause execution for a specific duration. ESSENTIAL for checking background task progress.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "integer",
                        "description": "Time to wait in seconds (e.g., 60).",
                    }
                },
                "required": ["seconds"],
            },
        },
    },
]

ALL_TOOLS = BASE_TOOLS + [TASK_TOOL, SKILL_TOOL]

def get_tools_for_agent(agent_type: str) -> list[dict]:
    """Filter tools based on agent type."""
    allowed = AGENT_TYPES.get(agent_type, {}).get("tools", "*")
    if allowed == "*":
        return ALL_TOOLS
    tools = [t for t in BASE_TOOLS if t["function"]["name"] in allowed]
    return tools

__all__ = ["BASE_TOOLS", "TASK_TOOL", "SKILL_TOOL", "ALL_TOOLS", "get_tools_for_agent"]