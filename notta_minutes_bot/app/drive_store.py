import datetime
import io

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from .config import Config

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _credentials():
    if not Config.GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON が設定されていません")
    return service_account.Credentials.from_service_account_file(
        Config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
    )


def _drive_service():
    return build("drive", "v3", credentials=_credentials())


def _sheets_service():
    return build("sheets", "v4", credentials=_credentials())


def save_text_as_google_doc(filename: str, content: str, folder_id: str | None = None) -> str:
    """プレーンテキストをGoogle Docsとして指定フォルダに保存し、ファイルIDを返す。

    Google Docsとして保存するのは、Claude ProjectのGoogle Drive連携が
    Docs/Sheets/Slides/PDF等をナレッジとして取り込める想定のため。
    """
    service = _drive_service()
    folder_id = folder_id or Config.DRIVE_FOLDER_ID
    if not folder_id:
        raise RuntimeError("DRIVE_FOLDER_ID が設定されていません")

    file_metadata = {
        "name": filename,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id],
    }
    media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="text/plain")
    created = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    return created["id"]


def doc_url(file_id: str) -> str:
    return f"https://docs.google.com/document/d/{file_id}/edit"


def append_tasks(meeting_title: str, tasks: list[dict]) -> None:
    """タスクリストを、1つの継続管理用Google Sheetsに行として追記する。

    事前にスプレッドシートを作成し、1行目に
    日付 / 会議名 / 担当者 / タスク / 期限 / 完了 のヘッダーを入れておくこと
    （サービスアカウントのメールアドレスに編集者共有も必要）。
    """
    if not tasks:
        return
    if not Config.TASK_SHEET_ID:
        raise RuntimeError("TASK_SHEET_ID が設定されていません")

    today = datetime.date.today().isoformat()
    rows = [
        [today, meeting_title, t.get("assignee", "未定"), t.get("task", ""), t.get("due", "未定"), ""]
        for t in tasks
    ]

    service = _sheets_service()
    service.spreadsheets().values().append(
        spreadsheetId=Config.TASK_SHEET_ID,
        range=f"{Config.TASK_SHEET_TAB}!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()


def task_sheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{Config.TASK_SHEET_ID}/edit"
