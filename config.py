from pathlib import Path
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# =============================================================================
# Global configuration
# =============================================================================

# Backend config (DeepSeek / OpenAI compatible)
# 只依赖三个环境变量（可以放在 shell 或 .env 中）：
#   - API_KEY
#   - BASE_URL
#   - MODEL
API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL")
MODEL = os.getenv("MODEL")

WORKDIR = Path.cwd()
SKILLS_DIR = WORKDIR / "skills"

missing = [name for name, val in [("API_KEY", API_KEY), ("BASE_URL", BASE_URL), ("MODEL", MODEL)] if not val]
if missing:
    sys.exit(f"Error: missing env vars: {', '.join(missing)} (set them in shell or .env)")

# Shared client instance
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


__all__ = [
    "API_KEY",
    "BASE_URL",
    "MODEL",
    "WORKDIR",
    "SKILLS_DIR",
    "client",
]


