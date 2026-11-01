"""Notta API への問い合わせ処理。

注意: Nottaの公式APIドキュメントは本実装時点で未確認。ここで使っている
エンドポイント形状（ベースURL・パス・Bearer認証）は、第三者の解説記事を
参考にした推定であり、実際のNottaデベロッパー向けドキュメント・ダッシュ
ボードで必ず突き合わせること。認証ヘッダ名やレスポンス形式が異なる場合は
本ファイルを修正する。
"""

import requests

from .config import Config


class NottaApiError(RuntimeError):
    pass


def _headers():
    if not Config.NOTTA_API_KEY:
        raise NottaApiError("NOTTA_API_KEY が設定されていません")
    return {"Authorization": f"Bearer {Config.NOTTA_API_KEY}"}


def extract_transcription_id(webhook_payload: dict) -> str | None:
    """Webhookのペイロードから文字起こしIDを取り出す。

    Nottaが実際に送ってくるキー名が確認できていないため、よくありそうな
    候補を順に探す防御的な実装にしている。
    """
    candidates = [
        ("data", "transcription_id"),
        ("data", "transcriptionId"),
        ("data", "id"),
        ("transcription_id",),
        ("transcriptionId",),
        ("id",),
    ]
    for path in candidates:
        node = webhook_payload
        for key in path:
            if not isinstance(node, dict) or key not in node:
                node = None
                break
            node = node[key]
        if isinstance(node, str) and node:
            return node
    return None


def fetch_transcription_result(transcription_id: str) -> dict:
    """文字起こし結果を取得する。

    戻り値の想定形式: {"title": str, "text": str, "created_at": str, ...}
    実際のレスポンス構造が異なる場合はここでマッピングを調整する。
    """
    url = f"{Config.NOTTA_API_BASE_URL}/transcriptions/{transcription_id}/result"
    resp = requests.get(url, headers=_headers(), timeout=30)
    if resp.status_code != 200:
        raise NottaApiError(
            f"Notta API エラー: status={resp.status_code} body={resp.text[:500]}"
        )
    return resp.json()
