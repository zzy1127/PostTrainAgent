#!/usr/bin/env python
"""
Thin entrypoint for the v4 skills agent.

- Global config: config.py
- Agent types: agent_types.py
- Skills loader: skills/loader.py
- Tools definition: tools/base.py
- Tools implementation: tools/impl.py
"""

import json

from tasks.agent_types import AGENT_TYPES, get_agent_descriptions
from config import WORKDIR, MODEL, client
from skills.loader import SKILLS
from tools.base import ALL_TOOLS
from tools.impl import execute_tool
from utils.colors import (
    color,
    FG_GREEN,
    FG_CYAN,
    FG_BLUE,
    FG_YELLOW,
    FG_MAGENTA,
    FG_BRIGHT_BLACK,
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
- After finishing, summarize what changed."""


def agent_loop(messages: list[dict]) -> list[dict]:
    """Main agent loop with skills support."""
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=ALL_TOOLS,
            tool_choice="auto",
            temperature=0,
        )

        response_message = response.choices[0].message
        content = response_message.content
        tool_calls = response_message.tool_calls

        if content:
            print(color("\nAssistant:", FG_GREEN))
            print(color(content, FG_GREEN))

        if not tool_calls:
            messages.append(response_message)
            return messages

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
            else:
                print(color(f"\n> {name}: {args}", FG_CYAN))

            output = execute_tool(name, args)

            if name == "Skill":
                print(color(f"  Skill loaded ({len(output)} chars)", FG_BLUE))
            elif name != "Task":
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
            print(f"Error: {e}")

        print()


if __name__ == "__main__":
    main()
