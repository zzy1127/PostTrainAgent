from skills.loader import SKILLS


SKILL_TOOL = {
    "type": "function",
    "function": {
        "name": "Skill",
        "description": f"""Load a skill to gain specialized knowledge for a task.

Available skills:
{SKILLS.get_descriptions()}

When to use:
- IMMEDIATELY when user task matches a skill description
- Before attempting domain-specific work (PDF, MCP, etc.)""",
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "description": "Name of the skill to load",
                }
            },
            "required": ["skill"],
        },
    },
}


__all__ = ["SKILL_TOOL"]


