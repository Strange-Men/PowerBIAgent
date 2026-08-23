"""Print secret-safe local startup diagnostics without echoing .env values."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.app.config.settings import Settings
from backend.app.config.startup_diagnostics import (
    inspect_dotenv_format,
    safe_startup_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 PowerBIAgent 本地启动配置")
    parser.add_argument("--env-file", default=".env", help="要检查的 dotenv 文件")
    args = parser.parse_args()
    env_path = Path(args.env_file)
    diagnostic = inspect_dotenv_format(env_path)
    print(f"DOTENV_PRESENT={str(diagnostic.exists).lower()}")
    print(f"DOTENV_FORMAT_VALID={str(diagnostic.valid).lower()}")
    if not diagnostic.valid:
        line_numbers = ",".join(str(item) for item in diagnostic.invalid_line_numbers)
        print(f"DOTENV_INVALID_LINES={line_numbers}")
        print("请仅保留 KEY=value、以 # 开头的注释和空行。")
        return 1

    settings = Settings(_env_file=env_path if diagnostic.exists else None)
    for key, value in safe_startup_summary(settings).items():
        if isinstance(value, list):
            rendered = ",".join(str(item) for item in value) or "none"
        elif isinstance(value, bool):
            rendered = str(value).lower()
        else:
            rendered = str(value)
        print(f"{key.upper()}={rendered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
