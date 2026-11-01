import smtplib
from email.mime.text import MIMEText

from .config import Config


def send_minutes_notification(meeting_title: str, doc_url: str, task_sheet_url: str, task_count: int) -> None:
    """議事録・タスクリストの生成完了をメールで通知する（Gmail SMTP）。

    GMAIL_USERの2段階認証を有効化し、アプリパスワードを発行して
    GMAIL_APP_PASSWORDに設定すること。通知先が未設定なら何もしない。
    """
    if not (Config.GMAIL_USER and Config.GMAIL_APP_PASSWORD and Config.NOTIFY_EMAIL_TO):
        return

    body = (
        f"「{meeting_title}」の議事録・タスクリストができました。\n\n"
        f"議事録: {doc_url}\n"
        f"タスクリスト（{task_count}件追加）: {task_sheet_url}\n"
    )
    message = MIMEText(body)
    message["Subject"] = f"[議事録] {meeting_title}"
    message["From"] = Config.GMAIL_USER
    message["To"] = Config.NOTIFY_EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(Config.GMAIL_USER, Config.GMAIL_APP_PASSWORD)
        smtp.send_message(message)
