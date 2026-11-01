import anthropic

from .config import Config

SYSTEM_PROMPT = """\
あなたは会議の文字起こしから議事録とタスクリストを作成するアシスタントです。
入力される文字起こしテキストを読み、以下のMarkdown形式で日本語の出力を作成してください。

# 議事録: {会議タイトルがあれば使う。なければ「ミーティング」}

## 概要
（2〜4文で会議の目的と結論を要約）

## 決定事項
- （決定したことを箇条書き。なければ「特になし」）

## 議論内容
- （主なトピックごとに箇条書き。発言者が分かる場合は名前を付ける）

## タスクリスト
| 担当者 | タスク | 期限 |
|---|---|---|
（担当者・期限が文字起こしから分からない場合は「未定」と書く。タスクが
何もなければ表の代わりに「特になし」とだけ書く）

出力はこのMarkdown本文のみとし、前置きや確認の言葉は付けないでください。
文字起こしに含まれない情報を推測で付け足さないでください。
"""


def generate_minutes(transcript_text: str, meta: dict | None = None) -> str:
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

    text_parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_parts).strip()
