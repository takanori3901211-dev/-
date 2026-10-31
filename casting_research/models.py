"""キャスティングリサーチ用のデータモデル定義。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Optional

# 購買トリガーの参考タグ（HANDOFF.md記載の社内分析フレームワークを流用。
# 強制ではなく、hook_patternの入力時の候補として使う）
HOOK_PATTERN_SUGGESTIONS = [
    "報酬予測", "性能説明", "CTA", "PAS", "ツァイガルニク効果",
    "カクパ", "FOMO", "メロジョイ", "権威性", "ビタビタ",
    "ハロー効果", "三の法則", "ビフォーアフター", "タゴサク構文",
]

PLATFORM_CHOICES = ["X", "TikTok", "Instagram", "YouTube", "TV", "other"]
SOURCE_METHOD_CHOICES = ["web_search", "manual_url", "x_api", "other"]


@dataclass
class ClipEntry:
    id: str
    product_name: str
    talent_name: str
    clip_url: str
    brand: str = ""
    talent_handle: str = ""
    platform_origin: str = "X"
    content_type: str = ""
    hook_pattern: list[str] = field(default_factory=list)
    engagement_note: str = ""
    source_method: str = "web_search"
    discovered_at: str = field(default_factory=lambda: date.today().isoformat())
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ClipEntry":
        return ClipEntry(**d)


@dataclass
class TalentEntry:
    id: str
    name: str
    x_handle: str = ""
    tiktok_handle: str = ""
    instagram_handle: str = ""
    youtube_handle: str = ""
    genre: str = ""
    note: str = ""
    created_at: str = field(default_factory=lambda: date.today().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "TalentEntry":
        return TalentEntry(**d)
