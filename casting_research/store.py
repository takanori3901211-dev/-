"""JSONファイルを単純なデータストアとして扱うための薄いレイヤー。"""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
CLIPS_PATH = DATA_DIR / "clips.json"
TALENTS_PATH = DATA_DIR / "talents.json"


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _save(path: Path, items: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_clips() -> list[dict]:
    return _load(CLIPS_PATH)


def save_clips(items: list[dict]) -> None:
    _save(CLIPS_PATH, items)


def load_talents() -> list[dict]:
    return _load(TALENTS_PATH)


def save_talents(items: list[dict]) -> None:
    _save(TALENTS_PATH, items)


def next_id(items: list[dict], prefix: str) -> str:
    return f"{prefix}{len(items) + 1:04d}"


def find_talent_by_name(talents: list[dict], name: str) -> dict | None:
    for t in talents:
        if t["name"] == name:
            return t
    return None
