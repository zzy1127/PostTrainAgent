# tools/impl.py
from pathlib import Path
import subprocess
import time
import json
import shlex

from tasks.agent_types import AGENT_TYPES
from config import WORKDIR, MODEL, client
from skills.loader import SKILLS
from tools.base import get_tools_for_agent, TodoManager, TODO # 假设 TodoManager 移到了 base 或保持在此处
# 注意：如果 TodoManager 仍在此文件中定义，请保留原有的 TodoManager 类代码

# (为了简洁，这里省略 TodoManager 类的定义，因为它没有逻辑变化)
# 请保留你原始代码中的 class TodoManager ... 和 TODO = TodoManager()

def safe_path(p: str) -> Path:
    """Ensure path stays within workspace."""
    path = (WORKDIR / p).resolve()
    if not str(path).startswith(str(WORKDIR)):
        raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_bash(cmd: str, background: bool = False) -> str:
    """Execute shell command with optional background support."""
    if any(d in cmd for d in ["rm -rf /", "sudo", "shutdown"]):
        return "Error: Dangerous command"
    
    try:
        if background:
            # 1. 构造日志文件名
            timestamp = int(time.time())
            log_file = f"nohup_{timestamp}.log"
            
            # 2. 构造后台运行命令 (核心逻辑)
            # 形式: nohup cmd > log 2>&1 & echo $!
            # 这允许命令在后台运行，并将输出重定向到文件，最后打印 PID
            bg_cmd = f"nohup {cmd} > {log_file} 2>&1 & echo $!"
            
            # 3. 包装进 Conda 环境
            # 使用 bash -c 确保内部的重定向和 & 符号被正确解释
            wrapped_cmd = [
                "conda", "run", "-n", "zzy", "--no-capture-output", 
                "bash", "-c", bg_cmd
            ]
            
            # 4. 执行 (此时 subprocess.run 会等待 'echo $!' 返回 PID 后立即结束，而不会等待后台任务)
            r = subprocess.run(
                wrapped_cmd,
                cwd=WORKDIR,
                capture_output=True,
                text=True,
                timeout=10 # 应该瞬间返回
            )
            
            if r.returncode != 0:
                return f"Error starting background job: {r.stderr}"
            
            pid = r.stdout.strip()
            return (f"Background process started.\n"
                    f"PID: {pid}\n"
                    f"Log file: {log_file}\n"
                    f"Action: Use 'read_file {log_file}' to check progress later.")
            
        else:
            # 前台阻塞运行
            # 使用 bash -c 包装，以支持管道符 | 和重定向 >
            safe_cmd = shlex.quote(cmd)
            wrapped_cmd = f"conda run -n zzy --no-capture-output bash -c {safe_cmd}"
            
            r = subprocess.run(
                wrapped_cmd,
                shell=True,
                cwd=WORKDIR,
                capture_output=True,
                text=True,
                timeout=120, # 普通任务超时限制
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

def run_write(path: str, content: str, append: bool = False) -> str:
    """Write or append content to file."""
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        
        mode = 'a' if append else 'w'
        operation = "Appended to" if append else "Wrote"
        
        with fp.open(mode, encoding="utf-8") as f:
            f.write(content)
            
        return f"{operation} {path} ({len(content)} bytes)"
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
    
    # 简单的循环逻辑，防止无限递归
    MAX_STEPS = 10 
    step = 0

    while step < MAX_STEPS:
        step += 1
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

        sub_messages.append(response_message)

        if not tool_calls:
            return response_message.content or "(subagent finished)"

        for tc in tool_calls:
            args = json.loads(tc.function.arguments)
            name = tc.function.name
            output = execute_tool(name, args) # 递归调用 execute_tool

            sub_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": output,
            })
            
            elapsed = time.time() - start
            print(color(f"    -> [Subagent] {name} ... done. ({elapsed:.1f}s)", FG_MAGENTA))
            
    return "(subagent step limit reached)"

def execute_tool(name: str, args: dict) -> str:
    """Dispatch tool call to implementation."""
    if name == "bash":
        return run_bash(args["command"], args.get("background", False))
    if name == "read_file":
        return run_read(args["path"], args.get("limit"))
    if name == "write_file":
        return run_write(args["path"], args["content"], args.get("append", False))
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
    "TodoManager", "TODO", "safe_path", "run_bash", "run_read", 
    "run_write", "run_edit", "run_todo", "run_skill", "run_task", "execute_tool"
]