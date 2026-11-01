import datetime
import logging

from flask import Flask, jsonify, request

from . import drive_store, minutes_generator, notifier, notion_client
from .config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.post("/poll")
def poll_notion():
    """Notionの文字起こしデータベースを確認し、未処理ページを処理する。

    Cloud Schedulerなどから定期的に呼び出す想定（例: 15分おき）。
    """
    if Config.POLL_SHARED_SECRET:
        if request.args.get("secret") != Config.POLL_SHARED_SECRET:
            return jsonify({"error": "unauthorized"}), 401

    try:
        pages = notion_client.find_unprocessed_pages()
    except Exception:
        logger.exception("Notionの検索中にエラーが発生しました")
        return jsonify({"error": "internal_error"}), 500

    processed_ids = []
    for page in pages:
        page_id = page["id"]
        try:
            _process_page(page, page_id)
            notion_client.mark_processed(page_id)
            processed_ids.append(page_id)
        except Exception:
            logger.exception("ページ処理中にエラーが発生しました: page_id=%s", page_id)
            # このページは処理済みにせず、次回のポーリングで再試行する

    return jsonify({"found": len(pages), "processed": processed_ids})


def _process_page(page: dict, page_id: str) -> None:
    title = notion_client.extract_title(page)
    transcript_text = notion_client.fetch_page_text(page_id)
    if not transcript_text.strip():
        logger.warning("本文が空のためスキップ: page_id=%s", page_id)
        return

    meta = {"title": title, "created_at": page.get("created_time")}
    generated = minutes_generator.generate_minutes(transcript_text, meta)
    minutes_markdown = generated["minutes_markdown"]
    tasks = generated["tasks"]

    combined_markdown = (
        f"{minutes_markdown}\n\n---\n\n## 文字起こし全文\n\n{transcript_text}"
    )

    today = datetime.date.today().isoformat()
    doc_id = drive_store.save_text_as_google_doc(f"{today}_{title}", combined_markdown)
    drive_store.append_tasks(title, tasks)

    notifier.send_minutes_notification(
        meeting_title=title,
        doc_url=drive_store.doc_url(doc_id),
        task_sheet_url=drive_store.task_sheet_url(),
        task_count=len(tasks),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
