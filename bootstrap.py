import importlib
import os
import runpy
import subprocess
import sys
from pathlib import Path


def _ensure_packages_installed() -> None:
    required = ["customtkinter", "pynput", "autoit"]

    missing = []
    for pkg in required:
        try:
            importlib.import_module(pkg)
        except Exception:
            missing.append(pkg)

    if not missing:
        return

    project_dir = Path(__file__).resolve().parent
    req_path = project_dir / "requirements.txt"

    if not req_path.exists():
        raise FileNotFoundError(f"Missing requirements.txt at {req_path}")

    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(req_path)],
        cwd=str(project_dir),
    )


def main() -> None:
    _ensure_packages_installed()

    project_dir = Path(__file__).resolve().parent
    app_path = project_dir / "app.py"
    if not app_path.exists():
        raise FileNotFoundError(f"Missing app.py at {app_path}")

    os.environ.setdefault("PYTHONUTF8", "1")

    runpy.run_path(str(app_path), run_name="__main__")


if __name__ == "__main__":
    main()
