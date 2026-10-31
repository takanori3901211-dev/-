#!/usr/bin/env python3
"""Cloud Run上で動かすHTTPラッパー。

Google Apps Script(定期トリガー)から、Driveの「受付」フォルダIDを渡して
呼び出される想定。処理の中身はmake_video.pyに委譲するだけで、新しい編集
ロジックは持たない。

未検証: このファイルはGCPアクセスが無い開発環境で作成したもので、実際の
Cloud Run上でのデプロイ・動作確認はまだ行っていない。デプロイ前に
ローカルのDocker環境(このサンドボックスでは動かせなかった)等で一度
動作確認すること。

環境変数:
  SHARED_SECRET   Apps Scriptからのリクエストを検証する共有シークレット
                   (無指定の場合は認証なしで動く。本番では必ず設定すること)
  GEMINI_API_KEY   edit_brain.pyが使うGemini APIキー
"""

import os
import subprocess
import tempfile
from pathlib import Path

import google.auth
from flask import Flask, jsonify, request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

HERE = Path(__file__).resolve().parent
MAKE_VIDEO = HERE / "make_video.py"

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

app = Flask(__name__)


def _drive_client():
    """Cloud Run実行サービスアカウントの既定認証情報でDrive APIクライアントを作る。

    対象のDriveフォルダは、あらかじめこのサービスアカウントのメール
    アドレスと共有しておく必要がある。
    """
    creds, _ = google.auth.default(scopes=DRIVE_SCOPES)
    return build("drive", "v3", credentials=creds)


def _list_files(drive, folder_id):
    files = []
    page_token = None
    while True:
        resp = drive.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token,
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def _download_file(drive, file_id, dest_path):
    request_ = drive.files().get_media(fileId=file_id)
    with open(dest_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request_)
        done = False
        while not done:
            _status, done = downloader.next_chunk()


def _upload_file(drive, local_path, name, parent_folder_id):
    metadata = {"name": name, "parents": [parent_folder_id]}
    media = MediaFileUpload(str(local_path), resumable=True)
    drive.files().create(body=metadata, media_body=media, fields="id").execute()


def _check_auth():
    secret = os.environ.get("SHARED_SECRET")
    if not secret:
        return True
    return request.headers.get("X-Shared-Secret") == secret


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process():
    if not _check_auth():
        return jsonify({"error": "unauthorized"}), 401

    body = request.get_json(force=True, silent=True) or {}
    input_folder_id = body.get("input_folder_id")
    output_folder_id = body.get("output_folder_id") or input_folder_id

    if not input_folder_id:
        return jsonify({"error": "input_folder_idが必要です"}), 400

    drive = _drive_client()
    files = _list_files(drive, input_folder_id)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        product_info_path = None
        clip_paths = []

        for f in files:
            name = f["name"]
            local_path = tmp / name
            if name.lower().endswith(".txt"):
                _download_file(drive, f["id"], local_path)
                product_info_path = local_path
            elif name.lower().endswith((".mp4", ".mov")):
                _download_file(drive, f["id"], local_path)
                clip_paths.append(local_path)

        if product_info_path is None:
            return jsonify({"error": "商品情報.txtがフォルダ内に見つかりません"}), 400
        if not clip_paths:
            return jsonify({"error": "動画ファイルがフォルダ内に見つかりません"}), 400

        outdir = tmp / "out"
        cmd = ["python3", str(MAKE_VIDEO), str(product_info_path),
               *[str(p) for p in clip_paths], str(outdir)]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return jsonify({
                "error": "make_video.pyが失敗しました",
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            }), 500

        final_path = outdir / "final.mp4"
        if not final_path.exists():
            return jsonify({"error": "final.mp4が生成されませんでした",
                             "stdout": result.stdout[-4000:]}), 500

        _upload_file(drive, final_path, "final.mp4", output_folder_id)

        for extra_name in ("plan.json", "seg_ai.json"):
            extra_path = outdir / extra_name
            if extra_path.exists():
                _upload_file(drive, extra_path, extra_name, output_folder_id)

    return jsonify({"status": "done", "output_folder_id": output_folder_id})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
