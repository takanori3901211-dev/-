#!/usr/bin/env python3
"""Phase2: AI判断層。Gemini APIにテロップ整文・フック・CTAを生成させる。

社外非公開: このファイルはPhase3で素人ユーザーに配布・開示しない。
GEMINI_API_KEY環境変数が必須 (未設定の場合は実行時エラー)。
"""

import copy
import json
import os
import sys

HOOK_DURATION = 2.3
HOOK_GAP = 0.1
HOOK_SHIFT = HOOK_DURATION + HOOK_GAP  # 既存セグメントをこの秒数分後ろにずらす

SYSTEM_PROMPT = """\
あなたはTikTok Shop動画の構成作家です。入力された発話の文字起こしと商品情報から、
以下のルールに厳密に従って編集方針をJSONで出力してください。

# フック (冒頭3秒・新規追加するテロップ)
- 結論を言わない未完了状態にする(ツァイガルニク効果)、または「まだ○○してる人」型の
  呼びかけにする(カクテルパーティ効果)。
- 数字は書かない。

# テロップ本文 (元の発話を整文したもの)
- 元の発話のフィラー(「えー」「あの」等)を除いて整文する。意味は変えない。
- 全角12〜16文字程度を目安にする。
- 元の発話に悩み→解決の順序(PAS)があれば、その順序を保持する。
- 誇張表現は使わない。

# CTA (末尾に追加するテロップ)
- 「詳細は左下の黄色ボタンをチェックしてね」の意味を必ず含める。
- 数字は書かない。

# ハッシュタグ
- メーカー名・商品名・ジャンル名の3種類のみ。

# 禁止事項
- 薬機法・景品表示法に抵触しうる断定表現。
- 存在しない性能の記載。
- 具体的な価格・割引率の記載。

# 文体
- タメ口・標準語。「です/ます」は禁止。方言も禁止。

# 出力形式 (JSON厳守、他の文章は一切出力しない)
{
  "hook": {"text": "..."},
  "captions": [{"text": "..."}],
  "cta": {"text": "..."},
  "hashtags": ["...", "...", "..."],
  "self_check": "ルール違反がないかの自己チェック結果"
}
"""


def call_gemini(segments, product_info):
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEYが設定されていません。", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    user_content = json.dumps(
        {"segments": segments, "product_info": product_info},
        ensure_ascii=False,
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.7,
        ),
    )

    return json.loads(response.text)


def _shift_segments(segments, shift):
    shifted = []
    for seg in segments:
        s = copy.deepcopy(seg)
        s["start"] += shift
        s["end"] += shift
        shifted.append(s)
    return shifted


def build_seg_ai(segments, plan):
    hook_seg = {"start": 0.0, "end": HOOK_DURATION, "text": plan["hook"]["text"]}

    shifted = _shift_segments(segments, HOOK_SHIFT)
    for seg, caption in zip(shifted, plan["captions"]):
        seg["text"] = caption["text"]

    last_end = shifted[-1]["end"] if shifted else HOOK_SHIFT
    cta_seg = {
        "start": last_end + HOOK_GAP,
        "end": last_end + HOOK_GAP + HOOK_DURATION,
        "text": plan["cta"]["text"],
    }

    return {"segments": [hook_seg] + shifted + [cta_seg], "hashtags": plan["hashtags"]}


def main():
    if len(sys.argv) != 4:
        print("usage: edit_brain.py seg.json product_info.txt seg_ai.json",
              file=sys.stderr)
        sys.exit(1)

    seg_path, product_info_path, out_path = sys.argv[1:4]

    with open(seg_path, encoding="utf-8") as f:
        segments = json.load(f)["segments"]

    with open(product_info_path, encoding="utf-8") as f:
        product_info = f.read().strip()

    plan = call_gemini(segments, product_info)
    seg_ai = build_seg_ai(segments, plan)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(seg_ai, f, ensure_ascii=False, indent=2)

    print(f"[edit_brain] hook_freeze={HOOK_DURATION} -> {out_path}")


if __name__ == "__main__":
    main()
