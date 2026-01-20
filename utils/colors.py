RESET = "\033[0m"
BOLD = "\033[1m"

FG_GREEN = "\033[32m"
FG_CYAN = "\033[36m"
FG_BLUE = "\033[34m"
FG_YELLOW = "\033[33m"
FG_MAGENTA = "\033[35m"
FG_BRIGHT_BLACK = "\033[90m"


def color(text: str, *codes: str) -> str:
    """Wrap text with ANSI color codes."""
    if not codes:
        return str(text)
    return "".join(codes) + str(text) + RESET


__all__ = [
    "RESET",
    "BOLD",
    "FG_GREEN",
    "FG_CYAN",
    "FG_BLUE",
    "FG_YELLOW",
    "FG_MAGENTA",
    "FG_BRIGHT_BLACK",
    "color",
]


