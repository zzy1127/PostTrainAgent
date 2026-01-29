#!/usr/bin/env python
"""
Thin entrypoint for the v4 skills agent.
Supports robust JSON parsing and JSONL logging for benchmarks.
"""

import json
import os
import time
import traceback
import sys
import ast
import re
from pathlib import Path
from typing import Any

from tasks.agent_types import AGENT_TYPES, get_agent_descriptions
from config import WORKDIR, MODEL, client
from skills.loader import SKILLS
from tools.base import ALL_TOOLS
from tools.impl import execute_tool
from tools.job_manager import JOBS
from utils.colors import (
    color,
    FG_GREEN,
    FG_CYAN,
    FG_BLUE,
    FG_YELLOW,
    FG_MAGENTA,
    FG_BRIGHT_BLACK,
    FG_RED,
)

SYSTEM = f"""You are a coding agent at {WORKDIR}.

Loop: plan -> act with tools -> report.

**Skills available** (invoke with Skill tool when task matches):
{SKILLS.get_descriptions()}

**Subagents available** (invoke with Task tool for focused subtasks):
{get_agent_descriptions()}

Rules:
- Use Skill tool IMMEDIATELY when a task matches a skill description
- Use Task tool for subtasks needing focused exploration or implementation
- Use TodoWrite to track multi-step work
- Prefer tools over prose. Act, don't just explain.
- After finishing, summarize what changed.
- **Background Jobs**: If you start a background task, check its status via the System Context. Use 'wait' to let time pass if tasks are running.
- **File Writing**: When writing code, ensure you escape newlines (\\n) and quotes (\") correctly in JSON."""


def get_context_injection() -> str:
    """构建环境感知消息：时间 + 后台任务状态"""
    current_time = time.strftime("%Y-%m-%d %H:%M:%S")
    job_status = JOBS.check_jobs()
    
    return (
        f"\n[SYSTEM STATUS UPDATE]\n"
        f"Current Time: {current_time}\n"
        f"Background Jobs Status:\n{job_status}\n"
        f"----------------\n"
        f"Guidance: \n"
        f"1. If jobs are 'RUNNING', check their logs via 'read_file'.\n"
        f"2. If you need to wait for them, use the 'wait' tool (don't loop read_file without waiting).\n"
        f"3. If jobs are 'DONE', verify the results."
    )


def log_jsonl(event_type: str, payload: dict):
    """[NEW] 统一的 JSONL 日志输出，用于非交互模式"""
    try:
        log_entry = {
            "timestamp": time.time(),
            "event": event_type,
            "data": payload
        }
        print(json.dumps(log_entry, ensure_ascii=False), flush=True)
    except Exception:
        # 极端情况下的 fallback
        print(f'{{"event": "error", "message": "Log serialization failed"}}', flush=True)


def safe_parse_json(json_str: str) -> dict:
    """
    终极 JSON 解析器：
    1. 基础清洗 (去除 Markdown, 尾部反斜杠, 非法尾部字符)
    2. 尝试 json.loads (strict=False)
    3. 尝试 ast.literal_eval (处理 Python 风格字典，如单引号、直接换行)
    4. 针对 write_file 的特殊正则提取
    """
    if not isinstance(json_str, str):
        return json_str

    # === Step 1: 预处理 ===
    cleaned = json_str.strip()
    
    # 去除 Markdown 代码块包裹
    if "```" in cleaned:
        pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
        match = re.search(pattern, cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1)

    # 去除 DeepSeek 常见的尾部反斜杠 BUG
    cleaned = cleaned.rstrip("\\")
    
    # 去除 JSON 结尾可能多余的字符 (解决 Extra data 问题)
    last_brace = cleaned.rfind('}')
    if last_brace != -1:
        cleaned = cleaned[:last_brace+1]

    # === Step 2: 标准 JSON 解析 (宽松模式) ===
    try:
        # strict=False 允许字符串包含部分控制字符
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        pass

    # === Step 3: Python AST 解析 (神器) ===
    # Python 的字典允许字符串直接换行，且允许单引号
    # 这能解决大部分 "Expecting ',' delimiter" 错误
    try:
        # 先把 JSON 的 null/true/false 转换成 Python 的 None/True/False
        python_style = cleaned.replace("null", "None").replace("true", "True").replace("false", "False")
        return ast.literal_eval(python_style)
    except (ValueError, SyntaxError):
        pass

    # === Step 4: 针对 write_file 的暴力正则提取 ===
    # 如果前面都挂了，且看起来是 write_file，我们直接提取 path 和 content
    if '"path"' in cleaned and '"content"' in cleaned:
        try:
            # 提取 path (简单字符串)
            path_match = re.search(r'"path"\s*:\s*"([^"]+)"', cleaned)
            
            # 提取 content (假设是双引号包裹，且是 JSON 的一部分)
            # 这里的逻辑是：找到 "content": 之后，第一个 " 开始，到倒数第二个 " 结束 (忽略最后的 })
            # 这是一个非常激进的提取，专门应对 JSON 格式彻底烂掉的情况
            content_pattern = r'"content"\s*:\s*"(.*)"\s*\}'
            content_match = re.search(content_pattern, cleaned, re.DOTALL)
            
            if path_match and content_match:
                print(color("Warning: JSON broken, using Regex fallback extraction!", FG_YELLOW))
                # 尝试手动反转义
                raw_content = content_match.group(1)
                try:
                    # 将 \\n 变回 \n，将 \" 变回 "
                    decoded_content = raw_content.encode('utf-8').decode('unicode_escape')
                except:
                    decoded_content = raw_content
                
                return {
                    "path": path_match.group(1),
                    "content": decoded_content,
                    # 如果有 append 参数，这里可能会漏掉，默认为 False 比较安全
                    "append": False 
                }
        except:
            pass

    # === Step 5: 实在没办法了，抛出异常 ===
    # 将原始字符串打印出来，方便调试
    raise ValueError(f"Failed to parse arguments. Raw: {json_str[:200]}...")


def agent_loop(messages: list[dict], interactive: bool = True) -> list[dict]:
    """
    Main agent loop.
    :param interactive: True 为带颜色输出，False 为 JSONL 输出
    """
    while True:
        # 状态注入
        status_payload = {"role": "system", "content": get_context_injection()}
        request_messages = messages + [status_payload]

        active_jobs = len(JOBS.jobs)
        
        # 交互模式显示后台任务提示
        if interactive and active_jobs > 0:
            print(color(f"\r[System] {active_jobs} background jobs active... ", FG_MAGENTA), end="")

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=request_messages,
                tools=ALL_TOOLS,
                tool_choice="auto",
                temperature=0,
            )
        except Exception as e:
            err_msg = f"API Error: {e}"
            if interactive:
                print(color(f"\n{err_msg}", FG_RED))
            else:
                log_jsonl("error", {"message": err_msg})
            return messages

        response_message = response.choices[0].message
        content = response_message.content
        tool_calls = response_message.tool_calls

        # --- 日志输出 ---
        if content:
            if interactive:
                print(color("\nAssistant:", FG_GREEN))
                print(color(content, FG_GREEN))
            else:
                log_jsonl("assistant_message", {"content": content})

        if not tool_calls:
            messages.append(response_message)
            return messages

        messages.append(response_message)

        for tc in tool_calls:
            try:
                # [FIXED] 使用新的增强解析器
                args = safe_parse_json(tc.function.arguments)
                name = tc.function.name
                
                # --- 工具调用日志 ---
                if interactive:
                    if name == "Task":
                        print(color(f"\n> Task: {args.get('description', 'subtask')}", FG_YELLOW))
                    elif name == "Skill":
                        print(color(f"\n> Loading skill: {args.get('skill', '?')}", FG_BLUE))
                    elif name == "wait":
                        print(color(f"\n> ⏳ Waiting for {args.get('seconds')}s...", FG_MAGENTA))
                    else:
                        print(color(f"\n> {name}: {args}", FG_CYAN))
                else:
                    log_jsonl("tool_call", {"name": name, "args": args})

                # --- 执行工具 ---
                output = execute_tool(name, args)

                # --- 工具结果日志 ---
                if interactive:
                    if name == "Skill":
                        print(color(f"  Skill loaded ({len(output)} chars)", FG_BLUE))
                    elif name != "Task" and name != "wait":
                        preview = str(output)[:500] + "..." if len(str(output)) > 500 else str(output)
                        print(color(f"  {preview}", FG_BRIGHT_BLACK))
                else:
                    # JSONL 模式下截断太长的输出以节省日志空间
                    preview = str(output)[:1000] + "...(truncated)" if len(str(output)) > 1000 else str(output)
                    log_jsonl("tool_result", {"name": name, "output": preview})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(output),
                })

            except Exception as e:
                # [CRITICAL FIX] 依然保留错误反馈机制，万一真的格式太烂，Agent 还可以自己修
                error_msg = f"Tool Error: {str(e)}. Please correct your arguments format."
                
                if interactive:
                    print(color(f"\n❌ {error_msg}", FG_RED))
                else:
                    log_jsonl("tool_error", {"error": error_msg, "raw_args": tc.function.arguments})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": error_msg,
                })


def get_prompt_from_env_or_file() -> str | None:
    """读取任务提示词"""
    prompt = os.getenv("PROMPT")
    if prompt:
        return prompt
    
    prompt_file = Path("prompt.txt")
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8").strip()
    
    return None


def run_interactive_mode() -> None:
    """交互模式：保留颜色输出"""
    print(color(f"Agent (Interactive) - Model: {MODEL}", FG_CYAN))
    print(color(f"Skills: {', '.join(SKILLS.list_skills())}", FG_BLUE))
    print(color("Type 'exit' to quit.\n", FG_BRIGHT_BLACK))

    history: list[dict] = [{"role": "system", "content": SYSTEM}]

    while True:
        try:
            user_input = input(color("You: ", FG_YELLOW)).strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() in ("exit", "quit", "q"):
            break

        history.append({"role": "user", "content": user_input})

        try:
            agent_loop(history, interactive=True)
        except Exception as e:
            traceback.print_exc()
        print()


def run_non_interactive_mode(prompt: str) -> None:
    """非交互模式：纯 JSONL 输出"""
    # 初始日志
    log_jsonl("startup", {
        "model": MODEL,
        "workdir": str(WORKDIR),
        "prompt": prompt
    })

    history: list[dict] = [{"role": "system", "content": SYSTEM}]
    history.append({"role": "user", "content": prompt})

    try:
        agent_loop(history, interactive=False)
        log_jsonl("finish", {"status": "success"})
    except Exception as e:
        log_jsonl("fatal_error", {"error": str(e), "traceback": traceback.format_exc()})
        raise


def main() -> None:
    prompt = get_prompt_from_env_or_file()
    
    if prompt:
        run_non_interactive_mode(prompt)
    else:
        run_interactive_mode()


if __name__ == "__main__":
    main()