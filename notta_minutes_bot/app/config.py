import os


class Config:
    NOTTA_API_KEY = os.environ.get("NOTTA_API_KEY", "")
    NOTTA_API_BASE_URL = os.environ.get("NOTTA_API_BASE_URL", "https://api.notta.ai/v1")
    NOTTA_WEBHOOK_SECRET = os.environ.get("NOTTA_WEBHOOK_SECRET", "")

    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5")

    GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "")

    # タスクリストを溜めていく単一のGoogle Sheets（事前に作成し、1行目に
    # 日付・会議名・担当者・タスク・期限・完了 のヘッダーを入れておく）
    TASK_SHEET_ID = os.environ.get("TASK_SHEET_ID", "")
    TASK_SHEET_TAB = os.environ.get("TASK_SHEET_TAB", "シート1")

    # 議事録生成の通知メール（Gmail SMTP + アプリパスワード）
    GMAIL_USER = os.environ.get("GMAIL_USER", "")
    GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
    NOTIFY_EMAIL_TO = os.environ.get("NOTIFY_EMAIL_TO", "")

    INBOUND_WEBHOOK_SHARED_SECRET = os.environ.get("INBOUND_WEBHOOK_SHARED_SECRET", "")
