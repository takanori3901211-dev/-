"""蓄積したキャスティング事例から集計レポート(Markdown)を生成する。"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from pathlib import Path

import store

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "output"


def _top(counter: Counter, n: int = 10) -> list[tuple[str, int]]:
    return counter.most_common(n)


def _render_table(rows: list[tuple[str, int]], col1: str) -> str:
    if not rows:
        return "（データなし）\n"
    lines = [f"| {col1} | 件数 |", "|---|---|"]
    lines += [f"| {name} | {count} |" for name, count in rows]
    return "\n".join(lines) + "\n"


def generate(output_dir: str | Path | None = None) -> Path:
    clips = store.load_clips()
    talents = store.load_talents()
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    product_counter = Counter(c["product_name"] for c in clips)
    talent_counter = Counter(c["talent_name"] for c in clips)
    content_type_counter = Counter(c["content_type"] for c in clips if c["content_type"])
    hook_counter = Counter(h for c in clips for h in c.get("hook_pattern", []))

    recent = sorted(clips, key=lambda c: c["discovered_at"], reverse=True)[:10]
    recent_lines = [
        f"- [{c['discovered_at']}] {c['product_name']} / {c['talent_name']} "
        f"({c['content_type'] or '-'}) — {c['clip_url']}"
        for c in recent
    ]

    talent_by_name = {t["name"]: t for t in talents}
    talent_detail_lines = []
    for name, count in _top(talent_counter, 20):
        t = talent_by_name.get(name)
        handle = f" ({t['x_handle']})" if t and t.get("x_handle") else ""
        talent_detail_lines.append(f"- {name}{handle}: {count}件")

    body = f"""# キャスティング事例リサーチレポート

生成日: {date.today().isoformat()}

## 概要

- 登録済み切り抜き事例数: {len(clips)}
- 登録済みタレント/インフルエンサー数: {len(talents)}

## 商品別 出演事例数ランキング

{_render_table(_top(product_counter), "商品名")}

## タレント/インフルエンサー別 出演事例数ランキング

{chr(10).join(talent_detail_lines) if talent_detail_lines else "（データなし）"}

## コンテンツ種別の傾向（切り抜き元の形式）

{_render_table(_top(content_type_counter), "コンテンツ種別")}

## 伸びた要因タグの傾向（PASやCTAなど）

{_render_table(_top(hook_counter), "要因タグ")}

## 直近追加された事例

{chr(10).join(recent_lines) if recent_lines else "（データなし）"}
"""

    out_path = out_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path.write_text(body, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    print(generate())
