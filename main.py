#!/usr/bin/env python
"""
Thin entrypoint for the v4 skills agent.

- Global config: config.py
- Agent types: agent_types.py
- Skills loader: skills/loader.py
- Tools definition: tools/base.py
- Tools implementation: tools/impl.py
- Job Manager: tools/job_manager.py
"""

import json
import time
import traceback

from tasks.agent_types import AGENT_TYPES, get_agent_descriptions
from config import WORKDIR, MODEL, client
from skills.loader import SKILLS
from tools.base import ALL_TOOLS
from tools.impl import execute_tool
from tools.job_manager import JOBS  # [NEW] 引入任务管理器
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
- **Background Jobs**: If you start a background task, check its status via the System Context. Use 'wait' to let time pass if tasks are running."""


def get_context_injection() -> str:
    """
    [NEW] 构建环境感知消息：时间 + 后台任务状态
    """
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


def agent_loop(messages: list[dict]) -> list[dict]:
    """Main agent loop with skills support and time perception."""
    while True:
        # [NEW] 每一轮对话前，生成当前的状态注入消息
        # 我们将其临时拼接到消息列表末尾，而不是永久存入 history
        # 这样模型能看到当前状态，但不会污染历史记录
        status_payload = {"role": "system", "content": get_context_injection()}
        request_messages = messages + [status_payload]

        active_jobs = len(JOBS.jobs)
        if active_jobs > 0:
            print(color(f"\r[System] {active_jobs} background jobs active... ", FG_MAGENTA), end="")

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=request_messages, # 使用带状态的临时列表
                tools=ALL_TOOLS,
                tool_choice="auto",
                temperature=0,
            )
        except Exception as e:
            print(color(f"\nAPI Error: {e}", FG_RED))
            return messages

        response_message = response.choices[0].message
        content = response_message.content
        tool_calls = response_message.tool_calls

        if content:
            print(color("\nAssistant:", FG_GREEN))
            print(color(content, FG_GREEN))

        # 如果没有工具调用，结束本轮 Loop，等待用户输入
        if not tool_calls:
            messages.append(response_message)
            return messages

        # 将 Assistant 的回复（包含 tool_calls）加入永久历史
        messages.append(response_message)

        for tc in tool_calls:
            args = json.loads(tc.function.arguments)
            name = tc.function.name

            if name == "Task":
                print(
                    color(
                        f"\n> Task: {args.get('description', 'subtask')}",
                        FG_YELLOW,
                    )
                )
            elif name == "Skill":
                print(
                    color(
                        f"\n> Loading skill: {args.get('skill', '?')}",
                        FG_BLUE,
                    )
                )
            elif name == "wait":
                # wait 工具特殊显示
                print(color(f"\n> ⏳ Waiting for {args.get('seconds')}s...", FG_MAGENTA))
            else:
                print(color(f"\n> {name}: {args}", FG_CYAN))

            output = execute_tool(name, args)

            if name == "Skill":
                print(color(f"  Skill loaded ({len(output)} chars)", FG_BLUE))
            elif name != "Task" and name != "wait":
                # 只有非 task/wait 的工具才显示预览
                preview = output[:200] + "..." if len(output) > 200 else output
                print(color(f"  {preview}", FG_BRIGHT_BLACK))

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": output,
                }
            )


def main() -> None:
    print(
        color(
            f"Agent (OpenAI Edition) with model: {MODEL} backend  - {WORKDIR}",
            FG_CYAN,
        )
    )
    print(color(f"Skills: {', '.join(SKILLS.list_skills()) or 'none'}", FG_BLUE))
    print(color(f"Agent types: {', '.join(AGENT_TYPES.keys())}", FG_MAGENTA))
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
            agent_loop(history)
        except Exception as e:
            traceback.print_exc()
            # print(f"Error: {e}")

        print()


if __name__ == "__main__":
    main()