"""Notionデータベースのポーリング用クライアント。

想定運用: 会議後にNottaの「Notionへ送信」機能（公式・全プラン対応だが
手動エクスポート）で文字起こしをNotionデータベースに書き出す。このモジュール
はそのデータベースを定期的にポーリングし、未処理（処理済みチェックボックス
がOFF）のページを見つけて本文を取得する。

Notion API自体は公式かつ安定したドキュメントがあるため、Notta直叩きの
ような仕様不明のリスクは無い。認証はIntegration token（Notion側で
「Internal Integration」を作成し、対象データベースをそのIntegrationに
共有するだけ）。
"""

import requests

from .config import Config

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers():
    if not Config.NOTION_API_KEY:
        raise RuntimeError("NOTION_API_KEY が設定されていません")
    return {
        "Authorization": f"Bearer {Config.NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def find_unprocessed_pages() -> list[dict]:
    """「処理済み」チェックボックスがOFFのページを取得する。"""
    if not Config.NOTION_DATABASE_ID:
        raise RuntimeError("NOTION_DATABASE_ID が設定されていません")

    url = f"{NOTION_API_BASE}/databases/{Config.NOTION_DATABASE_ID}/query"
    body = {
        "filter": {
            "property": Config.NOTION_PROCESSED_PROPERTY,
            "checkbox": {"equals": False},
        }
    }
    resp = requests.post(url, headers=_headers(), json=body, timeout=30)
    resp.raise_for_status()
    return resp.json().get("results", [])


def extract_title(page: dict) -> str:
    """ページのtitleプロパティ（プロパティ名はDB設計に依存するので型で探す）を取り出す。"""
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            text = "".join(t.get("plain_text", "") for t in prop.get("title", []))
            if text:
                return text
    return page["id"]


def fetch_page_text(page_id: str) -> str:
    """ページ本文（トップレベルブロック）をプレーンテキストとして結合する。

    Nottaがエクスポートする際の実際のブロック構造までは未確認のため、
    代表的なテキスト系ブロック（paragraph/heading/list item等）の
    rich_textのみを素直に連結する簡易実装。ネストしたブロックの中身は
    取得しない。
    """
    texts: list[str] = []
    url = f"{NOTION_API_BASE}/blocks/{page_id}/children"
    params = {"page_size": 100}

    while True:
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for block in data.get("results", []):
            block_type = block.get("type", "")
            rich_text = block.get(block_type, {}).get("rich_text", [])
            if rich_text:
                texts.append("".join(t.get("plain_text", "") for t in rich_text))

        if not data.get("has_more"):
            break
        params["start_cursor"] = data["next_cursor"]

    return "\n".join(texts)


def mark_processed(page_id: str) -> None:
    url = f"{NOTION_API_BASE}/pages/{page_id}"
    body = {"properties": {Config.NOTION_PROCESSED_PROPERTY: {"checkbox": True}}}
    resp = requests.patch(url, headers=_headers(), json=body, timeout=30)
    resp.raise_for_status()
