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