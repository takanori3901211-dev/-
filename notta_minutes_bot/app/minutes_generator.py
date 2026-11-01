import json

import anthropic

from .config import Config

TASKS_DELIMITER = "<<<TASKS_JSON>>>"

SYSTEM_PROMPT = f"""\
あなたは会議の文字起こしから議事録とタスクリストを作成するアシスタントです。
入力される文字起こしテキストを読み、以下の2部構成で出力してください。

[1部目] 議事録（Markdown、日本語）。次の見出し構成にすること。

# 議事録: {{会議タイトルがあれば使う。なければ「ミーティング」}}

## 概要
（2〜4文で会議の目的と結論を要約）

## 決定事項
- （決定したことを箇条書き。なければ「特になし」）

## 議論内容
- （主なトピックごとに箇条書き。発言者が分かる場合は名前を付ける）

[2部目] 1部目の直後に区切り文字 `{TASKS_DELIMITER}` を1行だけ書き、続けて
タスクリストをJSON配列として出力する。各要素は
{{"assignee": "担当者名（不明なら\\"未定\\"）", "task": "タスク内容", "due": "期限（不明なら\\"未定\\"）"}}
の形。タスクが無ければ空配列 `[]` とする。JSON以外の文字（説明文・コード
ブロックのバッククォートなど）は2部目に含めないこと。

文字起こしに含まれない情報を推測で付け足さないでください。
出力はこの2部構成の本文のみとし、前置きや確認の言葉は付けないでください。
"""


def generate_minutes(transcript_text: str, meta: dict | None = None) -> dict:
    """議事録Markdownとタスクリスト(dictのlist)を生成する。

    戻り値: {"minutes_markdown": str, "tasks": [{"assignee", "task", "due"}, ...]}
    """
    meta = meta or {}
    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY or None)

    user_content = ""
    if meta.get("title"):
        user_content += f"会議タイトル: {meta['title']}\n"
    if meta.get("created_at"):
        user_content += f"日時: {meta['created_at']}\n"
    user_content += "\n--- 文字起こし本文 ---\n" + transcript_text

    response = client.messages.create(
        model=Config.ANTHROPIC_MODEL,
        max_tokens=8000,
        output_config={"effort": "medium"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    full_text = "\n".join(
        block.text for block in response.content if block.type == "text"
    ).strip()

    if TASKS_DELIMITER in full_text:
        minutes_markdown, tasks_json = full_text.split(TASKS_DELIMITER, 1)
    else:
        minutes_markdown, tasks_json = full_text, "[]"

    minutes_markdown = minutes_markdown.strip()
    try:
        tasks = json.loads(tasks_json.strip())
        if not isinstance(tasks, list):
            tasks = []
    except json.JSONDecodeError:
        tasks = []

    return {"minutes_markdown": minutes_markdown, "tasks": tasks}
