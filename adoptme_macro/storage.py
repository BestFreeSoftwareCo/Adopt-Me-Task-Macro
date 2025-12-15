from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Tuple

from .models import AppState


def project_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def config_path() -> Path:
    return project_dir() / "config.json"


def profiles_dir() -> Path:
    p = project_dir() / "profiles"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = project_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _atomic_write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_config() -> AppState:
    path = config_path()
    if not path.exists():
        return AppState()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AppState.from_dict(data)
    except Exception:
        return AppState()


def save_config(state: AppState) -> None:
    _atomic_write_json(config_path(), state.to_dict())


def _profile_path(name: str) -> Path:
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_", ".")).strip()
    if not safe:
        raise ValueError("Profile name is required")
    return profiles_dir() / f"{safe}.json"


def list_profiles() -> List[Tuple[str, float]]:
    out: List[Tuple[str, float]] = []
    for p in profiles_dir().glob("*.json"):
        try:
            out.append((p.stem, p.stat().st_mtime))
        except Exception:
            continue
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def load_profile(name: str) -> AppState:
    path = _profile_path(name)
    data = json.loads(path.read_text(encoding="utf-8"))
    return AppState.from_dict(data)


def save_profile(name: str, state: AppState) -> None:
    _atomic_write_json(_profile_path(name), state.to_dict())


def delete_profile(name: str) -> None:
    path = _profile_path(name)
    if path.exists():
        path.unlink()
