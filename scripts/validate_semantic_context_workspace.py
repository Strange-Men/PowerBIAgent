"""Run M5.8.3 backend/Golden in an owned copy without developer dotenv files."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.acceptance_tempdir import owned_acceptance_tempdir


def main():
    with owned_acceptance_tempdir(prefix="powerbiagent-m583-validation-") as root:
        checkout = root / "checkout"
        subprocess.run(["git", "clone", "--shared", "--quiet", str(ROOT), str(checkout)], check=True)
        changed = set(subprocess.check_output(["git", "diff", "HEAD", "--name-only"], cwd=ROOT, text=True).splitlines())
        changed.update(subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True).splitlines())
        for name in sorted(changed):
            source = (ROOT / name).resolve()
            if (not source.is_relative_to(ROOT) or source.suffix not in {".py", ".md", ".yaml", ".yml"}
                    or any(part.startswith(".env") for part in Path(name).parts)):
                raise ValueError("validation_copy_path_not_allowed")
            target = checkout / name
            if not source.is_file():
                raise ValueError("validation_copy_requires_existing_file")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        if (checkout / ".env").exists():
            raise ValueError("validation_copy_contains_dotenv")
        environment = os.environ.copy()
        environment.update(LLM_MODE="mock", POWERBI_MODE="mock", PERSISTENCE_BACKEND="memory",
            PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONPATH=str(checkout))
        for command in ([sys.executable, "-m", "pytest", "backend/tests", "-q"],
                        [sys.executable, "-m", "backend.app.harness.cases"]):
            with subprocess.Popen(command, cwd=checkout, env=environment) as process:
                try:
                    result = process.wait()
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
            if result:
                raise SystemExit(result)


if __name__ == "__main__":
    main()
