import datetime
import logging

from flask import Flask, jsonify, request

from . import drive_store, minutes_generator, notta_client
from .config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.post("/webhook/notta")
def notta_webhook():
    if Config.INBOUND_WEBHOOK_SHARED_SECRET:
        if request.args.get("secret") != Config.INBOUND_WEBHOOK_SHARED_SECRET:
            return jsonify({"error": "unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    logger.info("Notta webhook受信: %s", payload)

    transcription_id = notta_client.extract_transcription_id(payload)
    if not transcription_id:
        logger.warning("ペイロードから文字起こしIDを特定できませんでした: %s", payload)
        return jsonify({"error": "transcription_id not found in payload"}), 400

    try:
        result = notta_client.fetch_transcription_result(transcription_id)
        transcript_text = result.get("text") or result.get("transcript") or ""
        meta = {
            "title": result.get("title"),
            "created_at": result.get("created_at"),
        }

        minutes_markdown = minutes_generator.generate_minutes(transcript_text, meta)

        today = datetime.date.today().isoformat()
        base_name = meta.get("title") or transcription_id
        drive_store.save_text_as_google_doc(
            f"{today}_{base_name}_文字起こし", transcript_text
        )
        drive_store.save_text_as_google_doc(
            f"{today}_{base_name}_議事録", minutes_markdown
        )
    except Exception:
        logger.exception("Notta webhook処理中にエラーが発生しました")
        return jsonify({"error": "internal_error"}), 500

    return jsonify({"status": "processed", "transcription_id": transcription_id})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
