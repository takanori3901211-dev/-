import io

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from .config import Config

SCOPES = ["https://www.googleapis.com/auth/drive"]


def _drive_service():
    if not Config.GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON が設定されていません")
    credentials = service_account.Credentials.from_service_account_file(
        Config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
    )
    return build("drive", "v3", credentials=credentials)


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
