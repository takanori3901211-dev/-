#!/usr/bin/env python3
"""X API (v2, 従量課金)を使ったキーワード検索+エンゲージメント数スクリーニング。

セットアップ:
  1. https://developer.x.com/ でプロジェクト作成・支払い方法登録(ユーザー自身の契約が必要)
  2. Bearer Tokenを発行
  3. 環境変数に設定: export X_API_BEARER_TOKEN="（取得したトークン）"

このスクリプトはcasting_researchのデータベース(clips.json)には直接書き込まない。
検索結果をエンゲージメント数順に一覧表示するだけで、出演タレントの特定はできない
ため、実際に事例として記録するかどうかは人（またはClaude）が内容を確認したうえで
`cli.py add-talent` / `cli.py add-clip` で登録する運用とする。

検索は直近7日分のみ（X API Recent search の制約）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://api.x.com/2/tweets/search/recent"


def search(query: str, max_results: int, bearer_token: str) -> dict:
    params = {
        "query": query,
        "max_results": str(max(10, min(max_results, 100))),
        "tweet.fields": "public_metrics,created_at,author_id",
        "expansions": "author_id,attachments.media_keys",
        "user.fields": "username,name",
        "media.fields": "type,url,preview_image_url",
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {bearer_token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"X API エラー ({e.code}): {body}", file=sys.stderr)
        sys.exit(1)


def _engagement_score(metrics: dict) -> int:
    return (
        metrics.get("like_count", 0)
        + metrics.get("retweet_count", 0) * 2
        + metrics.get("quote_count", 0) * 2
    )


def format_results(data: dict) -> str:
    tweets = data.get("data", [])
    if not tweets:
        return "該当する投稿は見つかりませんでした(直近7日間で検索)。"

    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    media = {m["media_key"]: m for m in data.get("includes", {}).get("media", [])}

    tweets.sort(key=lambda t: _engagement_score(t.get("public_metrics", {})), reverse=True)

    lines = []
    for t in tweets:
        m = t.get("public_metrics", {})
        user = users.get(t.get("author_id"), {})
        handle = user.get("username", "unknown")
        url = f"https://x.com/{handle}/status/{t['id']}"
        has_media = bool(t.get("attachments", {}).get("media_keys"))
        lines.append(
            f"- {url}\n"
            f"  投稿者: @{handle} ({user.get('name', '')})\n"
            f"  いいね:{m.get('like_count', 0)} RT:{m.get('retweet_count', 0)} "
            f"引用:{m.get('quote_count', 0)} 返信:{m.get('reply_count', 0)} "
            f"メディア添付:{'あり' if has_media else 'なし'}\n"
            f"  本文: {t.get('text', '').replace(chr(10), ' ')[:120]}\n"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True, help="検索キーワード(X検索構文可。例: 商品名 min_faves:500)")
    parser.add_argument("--max-results", type=int, default=20)
    parser.add_argument("--save", help="結果をJSONで保存するパス(任意)")
    args = parser.parse_args()

    token = os.environ.get("X_API_BEARER_TOKEN")
    if not token:
        print(
            "環境変数 X_API_BEARER_TOKEN が設定されていません。\n"
            "https://developer.x.com/ でBearer Tokenを取得し、\n"
            '  export X_API_BEARER_TOKEN="（取得したトークン）"\n'
            "を実行してから再度お試しください。",
            file=sys.stderr,
        )
        sys.exit(1)

    data = search(args.query, args.max_results, token)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"生データを保存しました: {args.save}")

    print(format_results(data))
    print(
        "\n※ ここに出た投稿をキャスティング事例として記録する場合は、"
        "出演タレントを目視確認したうえで `python3 cli.py add-clip` で登録してください。"
    )


if __name__ == "__main__":
    main()
