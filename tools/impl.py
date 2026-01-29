# tools/impl.py
from pathlib import Path
import subprocess
import time
import json
import shlex
import psutil
from tools.job_manager import JOBS

from tasks.agent_types import AGENT_TYPES
from config import WORKDIR, MODEL, client
from skills.loader import SKILLS
from tools.base import get_tools_for_agent
from tools.todo_manager import TODO
from utils.colors import color, FG_CYAN, FG_MAGENTA

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
    
    # 移除 Conda 包装，直接在当前环境中执行
    try:
        if background:
            # 1. 构造日志文件名
            timestamp = int(time.time())
            log_file = f"nohup_{timestamp}.log"
            
            # 2. 构造后台运行命令
            # 直接使用 bash 执行，不需要 conda run
            bg_cmd = f"nohup {cmd} > {log_file} 2>&1 & echo $!"
            
            # 3. 执行
            r = subprocess.run(
                ["/bin/bash", "-c", bg_cmd],
                cwd=WORKDIR,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if r.returncode != 0:
                return f"Error starting background job: {r.stderr}"
            
            pid = r.stdout.strip()
            JOBS.add_job(pid, cmd, log_file)
            return (f"Background task started. PID: {pid}\n"
                    f"Log: {log_file}\n"
                    f"System Note: I have registered this job. I will update you on its status in every turn.")
            
        else:
            # 前台阻塞运行
            # 直接调用 /bin/bash 执行命令
            # 这样可以保留管道符 | 和重定向 > 的功能，同时继承当前容器的环境变量
            r = subprocess.run(
                cmd,
                shell=True,
                cwd=WORKDIR,
                capture_output=True,
                text=True,
                timeout=120,
                executable="/bin/bash" 
            )
            return ((r.stdout + r.stderr).strip() or "(no output)")[:50000]
            
    except Exception as e:
        return f"Error: {e}"

def run_wait(seconds: int) -> str:
    """Agent 主动选择挂起，以等待后台任务"""
    try:
        seconds = int(seconds)
    except Exception:
        seconds = 10 # fallback

    if seconds > 3600:
        seconds = 3600
    
    print(color(f"    [System] Agent decided to wait for {seconds}s...", FG_MAGENTA))
    
    # 简单的睡眠
    time.sleep(seconds)
    
    # 【修改】返回更明确的 JSON 风格或指令风格字符串
    return (
        f"SUCCESS: System time advanced by {seconds} seconds.\n"
        f"Current Status: The wait is over. You should now verify the status of your background jobs using 'check_jobs' output or 'read_file' on logs."
    )

def run_read_file(path: str, limit: int | None = None) -> str:
    """
    读取文件内容。
    核心逻辑：支持负数 limit 实现倒序读取（Tail）。
    """
    try:
        # 1. 安全路径检查
        try:
            file_path = safe_path(path)
        except Exception as e:
            return f"Error: Invalid path security check - {e}"

        if not file_path.exists():
            return f"Error: File '{path}' does not exist."
        
        if not file_path.is_file():
            return f"Error: '{path}' is a directory, not a file. Use 'ls -la' instead."

        # 2. 读取文件 (处理编码错误)
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
            
        total_lines = len(lines)
        content = ""
        view_info = ""

        # 3. 切片逻辑
        if limit is None:
            # 全读 (由外部截断保护)
            content = "".join(lines)
            view_info = "(All content)"
        elif limit > 0:
            # 正序：读开头
            content = "".join(lines[:limit])
            view_info = f"(First {limit} lines)"
        elif limit < 0:
            # 倒序：读末尾 (Agent 的可观测性核心)
            # 例如 limit=-50，读取最后 50 行
            start_idx = max(0, total_lines + limit) 
            content = "".join(lines[start_idx:])
            view_info = f"(Last {abs(limit)} lines - TAIL MODE)"

        # 4. 最终组装
        # 加上 Total lines 提示，帮 Agent 建立文件大小的概念
        output = f"== File: {path} ==\n"
        output += f"== Meta: Total {total_lines} lines {view_info} ==\n"
        output += f"== Content Start ==\n{content}\n== Content End =="
        
        # 兜底截断，防止 main.py 里的解析器爆掉
        if len(output) > 50000:
            return output[:25000] + "\n...[SYSTEM TRUNCATED DUE TO LENGTH]...\n" + output[-25000:]
        
        return output

    except Exception as e:
        return f"Error reading file: {str(e)}"


def run_search_datasets(query: str, limit: int = 5) -> str:
    """
    在 Hugging Face 搜索数据集。
    """
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        
        # 按下载量排序，确保 Agent 搜到的是最主流的数据集
        datasets = api.list_datasets(
            search=query,
            sort="downloads",
            direction=-1,
            limit=limit
        )
        
        results = []
        for d in datasets:
            # 提取对 Agent 决策最有用的信息
            desc = d.description if d.description else "No description available."
            # 只取前 200 个字符，避免 Token 浪费
            desc_preview = desc[:200].replace("\n", " ") + "..."
            
            info = (
                f"- ID: {d.id}\n"
                f"  Downloads: {d.downloads}\n"
                f"  Likes: {d.likes}\n"
                f"  Description: {desc_preview}"
            )
            results.append(info)
            
        if not results:
            return f"No datasets found on Hugging Face for query: '{query}'"
            
        return (
            f"Found {len(results)} datasets for '{query}' (Sorted by Downloads):\n"
            "--------------------------------------------------\n" +
            "\n\n".join(results) +
            "\n--------------------------------------------------\n"
            "TIP: Copy the 'ID' exactly into your training script."
        )
    
    except ImportError:
        return "Error: huggingface_hub library is not installed."
    except Exception as e:
        return f"Error searching Hugging Face: {str(e)}"

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
        return run_read_file(args["path"], args.get("limit"))
    if name == "search_datasets":
        return run_search_datasets(args["query"], args.get("limit", 5))
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
    if name == "wait":
        return run_wait(args["seconds"])
    return f"Unknown tool: {name}"

__all__ = [
    "TodoManager", "TODO", "run_bash", "run_read_file", "run_search_datasets", "safe_path",
    "run_write", "run_edit", "run_todo", "run_skill", "run_task", "execute_tool"
]