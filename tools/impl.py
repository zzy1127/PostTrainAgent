from pathlib import Path
import subprocess
import time
import json

from tasks.agent_types import AGENT_TYPES
from config import WORKDIR, MODEL, client
from skills.loader import SKILLS
from tools.base import get_tools_for_agent
from utils.colors import color, FG_CYAN, FG_MAGENTA


class TodoManager:
    """Task list manager with constraints."""

    def __init__(self):
        self.items: list[dict] = []

    def update(self, items: list[dict]) -> str:
        validated: list[dict] = []
        in_progress = 0

        for i, item in enumerate(items):
            content = str(item.get("content", "")).strip()
            status = str(item.get("status", "pending")).lower()
            active = str(item.get("activeForm", "")).strip()

            if not content or not active:
                raise ValueError(f"Item {i}: content and activeForm required")
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Item {i}: invalid status")
            if status == "in_progress":
                in_progress += 1

            validated.append(
                {
                    "content": content,
                    "status": status,
                    "activeForm": active,
                }
            )

        if in_progress > 1:
            raise ValueError("Only one task can be in_progress")

        self.items = validated[:20]
        return self.render()

    def render(self) -> str:
        if not self.items:
            return "No todos."
        lines: list[str] = []
        for t in self.items:
            mark = (
                "[x]"
                if t["status"] == "completed"
                else "[>]"
                if t["status"] == "in_progress"
                else "[ ]"
            )
            lines.append(f"{mark} {t['content']}")
        done = sum(1 for t in self.items if t["status"] == "completed")
        return "\n".join(lines) + f"\n({done}/{len(self.items)} done)"


TODO = TodoManager()


def safe_path(p: str) -> Path:
    """Ensure path stays within workspace."""
    path = (WORKDIR / p).resolve()
    if not str(path).startswith(str(WORKDIR)):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def run_bash(cmd: str) -> str:
    """Execute shell command."""
    if any(d in cmd for d in ["rm -rf /", "sudo", "shutdown"]):
        return "Error: Dangerous command"
    try:
        wrapped_cmd = f"conda run -n zzy --no-capture-output {cmd}"
        r = subprocess.run(
            wrapped_cmd,
            shell=True,
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return ((r.stdout + r.stderr).strip() or "(no output)")[:50000]
    except Exception as e:
        return f"Error: {e}"


def run_read(path: str, limit: int | None = None) -> str:
    """Read file contents."""
    try:
        lines = safe_path(path).read_text(encoding="utf-8").splitlines()
        if limit:
            lines = lines[:limit]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"


def run_write(path: str, content: str) -> str:
    """Write content to file."""
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    """Replace exact text in file."""
    try:
        fp = safe_path(path)
        text = fp.read_text(encoding="utf-8")
        if old_text not in text:
            return f"Error: Text not found in {path}"
        fp.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


def run_todo(items: list[dict]) -> str:
    """Update the todo list."""
    try:
        return TODO.update(items)
    except Exception as e:
        return f"Error: {e}"


def run_skill(skill_name: str) -> str:
    """Load a skill and inject it into the conversation."""
    content = SKILLS.get_skill_content(skill_name)

    if content is None:
        available = ", ".join(SKILLS.list_skills()) or "none"
        return f"Error: Unknown skill '{skill_name}'. Available: {available}"

    return (
        f"<skill-loaded name=\"{skill_name}\">\n"
        f"{content}\n"
        f"</skill-loaded>\n\n"
        f"Follow the instructions in the skill above to complete the user's task."
    )


def run_task(description: str, prompt: str, agent_type: str) -> str:
    """Execute a subagent task."""
    if agent_type not in AGENT_TYPES:
        return f"Error: Unknown agent type '{agent_type}'"

    config = AGENT_TYPES[agent_type]
    sub_system = f"""You are a {agent_type} subagent at {WORKDIR}.

{config['prompt']}

Complete the task and return a clear, concise summary."""

    sub_tools = get_tools_for_agent(agent_type)

    sub_messages: list[dict] = [
        {"role": "system", "content": sub_system},
        {"role": "user", "content": prompt},
    ]

    print(color(f"[{agent_type}] {description}", FG_CYAN))
    start = time.time()
    tool_count = 0

    while True:
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=sub_messages,
                tools=sub_tools,
                tool_choice="auto",
                temperature=0,
            )
        except Exception as e:
            return f"Subagent Error: {e}"

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls

        # 将模型的回复加入历史
        sub_messages.append(response_message)

        if not tool_calls:
            return response_message.content or "(subagent finished)"

        for tc in tool_calls:
            tool_count += 1
            args = json.loads(tc.function.arguments)
            name = tc.function.name

            output = execute_tool(name, args)

            sub_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": output,
                }
            )

            elapsed = time.time() - start
            print(
                color(
                    f"    -> [Subagent] {name} ... done. ({elapsed:.1f}s)",
                    FG_MAGENTA,
                )
            )

    # Unreachable in normal flow
    # left for completeness
    return "(subagent finished)"


def execute_tool(name: str, args: dict) -> str:
    """Dispatch tool call to implementation."""
    if name == "bash":
        return run_bash(args["command"])
    if name == "read_file":
        return run_read(args["path"], args.get("limit"))
    if name == "write_file":
        return run_write(args["path"], args["content"])
    if name == "edit_file":
        return run_edit(args["path"], args["old_text"], args["new_text"])
    if name == "TodoWrite":
        return run_todo(args["items"])
    if name == "Task":
        return run_task(args["description"], args["prompt"], args["agent_type"])
    if name == "Skill":
        return run_skill(args["skill"])
    return f"Unknown tool: {name}"


__all__ = [
    "TodoManager",
    "TODO",
    "safe_path",
    "run_bash",
    "run_read",
    "run_write",
    "run_edit",
    "run_todo",
    "run_skill",
    "run_task",
    "execute_tool",
]


