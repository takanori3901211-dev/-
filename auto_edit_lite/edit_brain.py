#!/usr/bin/env python3
"""Phase2: AI判断層。Gemini APIにテロップ整文・フック・CTAを生成させる。

社外非公開: このファイルはPhase3で素人ユーザーに配布・開示しない。
GEMINI_API_KEY環境変数が必須 (未設定の場合は実行時エラー)。
"""

import copy
import json
import os
import sys
from pathlib import Path

HOOK_DURATION = 2.3
HOOK_GAP = 0.1
HOOK_SHIFT = HOOK_DURATION + HOOK_GAP  # 既存セグメントをこの秒数分後ろにずらす

HIGHLIGHT_SYSTEM_PROMPT = """\
あなたはTikTok Shop向け切り抜き動画のディレクターです。長尺素材の文字起こし
(0始まりのインデックス付きセグメント配列、各要素はstart/end/textを持つ)から、
切り抜き動画として最も効果の高い「ひと続きの区間」を1つ選んでください。

# 選定基準
- 商品の具体的なメリット・使用感・ビフォーアフターなど、視聴者の購買意欲を
  刺激する発言を含む区間を優先する。
- 単なる相槌や沈黙、本題に入る前の前置きだけの区間は避ける。
- 区間は文字起こしセグメントの連続した範囲(インデックス)として選ぶこと。
  セグメントを飛び飛びに選んではいけない。
- 区間の長さの目安は15秒〜30秒。目安から多少外れてもよいが、文の途中で
  不自然に切れないセグメント境界を優先する。

# 出力形式 (JSON厳守、他の文章は一切出力しない)
{
  "start_index": 0,
  "end_index": 3,
  "reason": "選んだ理由の一言"
}
start_index/end_indexは入力されたsegments配列のインデックスで、両端を含む範囲。
"""

SCRIPT_SYSTEM_PROMPT = """\
あなたはTikTok Shop向け動画の構成作家です。入力は商品情報のみで、素材映像は
ナレーション無しの手元B-roll(商品を手に取る・使用するクローズアップ映像)です。
テロップだけで完結する台本を商品情報から新規に作成してください。

# 全体構成
- フック (冒頭・未完了状態にする、「まだ○○してる人」型の呼びかけ、得られる未来を
  期待させる(報酬予測)、または二択で考えさせる(ダブルバインド)のいずれか。数字は書かない)
- 本文テロップ (2〜4個。商品の具体的な魅力→裏付けとなる処方・技術→仕上がりの
  描写、の順に紹介する。商品情報に効果の根拠・対象肌質・成分等の記載があれば、
  視聴者が疑問を抱きやすい情報として優先的に盛り込む。商品の特性に合えば、
  使用時の爽快感・満足感(キモジョイ等)が伝わる描写も使ってよい)
- CTA (末尾。「詳細は左下の黄色ボタンをチェックしてね」の意味を必ず含める。数字は書かない)

# 各テロップの表示秒数
- フック/本文/CTAそれぞれに"duration"(秒, 2.0〜4.0の範囲)を文字数に応じて指定する。

# 禁止事項
- 「価格の安さ」を訴求しない。誇張表現は使わない。
- ブランド名・商品名は入力された商品情報の表記を一字一句正確に使う(省略・言い換え禁止)。
- 存在しない効果の記載をしない。
- 他社・競合商品への言及や比較をしない。
- 薬機法・景品表示法に抵触しうる断定表現を避ける。

# 文体
- タメ口・標準語。「です/ます」は禁止。方言も禁止。

# 出力形式 (JSON厳守、他の文章は一切出力しない)
{
  "hook": {"text": "...", "duration": 2.3},
  "captions": [{"text": "...", "duration": 3.0}],
  "cta": {"text": "...", "duration": 2.3},
  "hashtags": ["...", "...", "..."]
}
"""

CLASSIFY_SYSTEM_PROMPT = """\
あなたはTikTok Shop向け動画素材の仕分け担当です。複数の画像が渡されます。
各クリップにつき、クリップ内の異なる時点から抽出した複数枚の代表フレームが
渡されます。画像の直前に"=== clip_0 ==="のようなテキストマーカーがあり、
そのマーカーの直後に続く画像群が1つのクリップに対応します。同じクリップの
複数枚の画像を総合して判断してください(1枚だけではブランド名が見えない
アングルのこともあるため)。

商品情報(複数商品が記載されている場合がある)が与えられるので、各画像に写って
いる商品がそのうちどれに最も一致するか判定してください。一致する商品が無い、
または商品そのものが写っていない(手元や背景のみ等)場合は"unknown"としてください。

また、そのカットがどんな見せ方をしているか(shot_type)を短く分類してください
(例: パッケージ/キャップのクローズアップ、コンパクトを開く、テクスチャ・質感、
手の甲や肌へのスウォッチ、使用シーン、など自由に簡潔な日本語で)。

# 出力形式 (JSON厳守、他の文章は一切出力しない)
{
  "results": [
    {"id": "clip_0", "product": "...", "shot_type": "...", "description": "一言説明"}
  ]
}
"""

VERIFY_SYSTEM_PROMPT = """\
あなたはTikTok Shop向け動画素材の検品担当です。「撮影指示書」のカットごとの
指示(shot_description、テロップ文言)と、実際にアップロードされた素材から
抽出したフレーム画像を照合してください。

各カットにつき複数枚の代表フレームが渡されます。画像の直前に
"=== shot_0 ==="のようなテキストマーカーがあり、そのマーカーの直後に続く
画像群が1つのカットに対応します。

各カットについて、実際の映像が指示内容(shot_description)とおおむね一致して
いるかを判定してください。厳密な一致は不要です。アングルや細部の違いは
問題にせず、以下のような明らかな不一致のみ"match": falseとしてください。
- 指示と全く違う被写体が写っている(例: パッケージのクローズアップの指示
  なのに人物の顔しか写っていない)
- 指示された商品そのものが写っていない、または別商品に見える

# 出力形式 (JSON厳守、他の文章は一切出力しない)
{
  "results": [
    {"id": "shot_0", "match": true, "note": "一言コメント"}
  ]
}
"""

PLAN_SYSTEM_PROMPT = """\
あなたはTikTok Shop向け動画の企画・構成作家です。ナレーション無しの手元B-roll
クリップ群(商品・見せ方が分類済み)と商品情報から、投稿動画の企画と構成を
提案してください。

# 企画 (concept)
- 商品情報に記載された複数の魅力のうち、どれを軸に訴求するかを1行で決める。

# 構成
- フック (冒頭・未完了状態にする、「まだ○○してる人」型の呼びかけ、得られる未来を
  期待させる(報酬予測)、または二択で考えさせる(ダブルバインド)のいずれか。数字は書かない)
- 本文テロップ (2〜4個。商品の具体的な魅力→裏付けとなる処方・技術→仕上がりの
  描写、の順に紹介する。商品情報に効果の根拠・対象肌質・成分等の記載があれば、
  視聴者が疑問を抱きやすい情報として優先的に盛り込む。商品の特性に合えば、
  使用時の爽快感・満足感(キモジョイ等)が伝わる描写も使ってよい)
- CTA (末尾。「詳細は左下の黄色ボタンをチェックしてね」の意味を必ず含める。数字は書かない)
- 各テロップには、与えられたクリップの中から最も内容が合うものを1つ選び、
  そのidを"clip_id"に指定すること。テロップの内容は、対応するクリップの
  shot_type/descriptionと矛盾しないようにする(例: テクスチャを見せている
  カットには使用感の話、パッケージのカットにはブランド名や特長の話)。
  クリップは使い回してよいが、できるだけ多様なカットを使う。

# 各テロップの表示秒数
- "duration"(秒, 2.0〜4.0の範囲)を文字数に応じて指定する。

# 禁止事項
- 「価格の安さ」を訴求しない。誇張表現は使わない。
- ブランド名・商品名は入力された商品情報の表記を一字一句正確に使う(省略・言い換え禁止)。
- 存在しない効果の記載をしない。
- 他社・競合商品への言及や比較をしない。
- 薬機法・景品表示法に抵触しうる断定表現を避ける。

# 文体
- タメ口・標準語。「です/ます」は禁止。方言も禁止。

# 出力形式 (JSON厳守、他の文章は一切出力しない)
{
  "concept": "...",
  "items": [
    {"clip_id": "clip_0", "text": "...", "duration": 2.3}
  ],
  "hashtags": ["...", "...", "..."]
}
itemsの最初の要素がフック、最後の要素がCTA、間が本文テロップ。
"""

SHOTLIST_SYSTEM_PROMPT = """\
あなたはTikTok Shop向け動画の企画・ディレクターです。商品情報のみから、
これから撮影する「カット割（撮影指示書）」を作成してください。素材はまだ
存在せず、撮影未経験のスタッフがこれを読んで迷わず撮影できる具体性が必要です。

# 企画 (concept)
- 商品情報に記載された複数の魅力のうち、どれを軸に訴求するかを1行で決める。

# カット構成
- フック用カットを1つ(冒頭)
- 本文用カットを2〜4つ(商品の魅力→裏付けとなる処方・技術→仕上がりの描写、の順)
- CTA用カットを1つ(末尾)

各カットについて以下を決める:
- "caption": そのカットに乗せるテロップ文言。数字は書かない。タメ口・標準語
  (「です/ます」禁止、方言禁止)。フックは未完了状態、「まだ○○してる人」型の
  呼びかけ、得られる未来を期待させる(報酬予測)、または二択で考えさせる
  (ダブルバインド)のいずれか。CTAは「詳細は左下の黄色ボタンをチェックしてね」
  の意味を含める。「価格の安さ」を訴求しない、誇張表現を使わない、ブランド名・
  商品名は商品情報の表記を一字一句正確に使う、存在しない効果を書かない、競合への
  言及・比較をしない、薬機法・景品表示法に抵触しうる断定表現を避ける。
- "duration": 表示秒数(2.0〜4.0秒、文字数に応じて)。
- "shot_description": 何をどう撮るか、日本語で簡潔かつ具体的に指示する
  (例:「商品パッケージを正面からかざして見せる」「フタを開けて中身を見せる」
  「手の甲に少量出してテクスチャを見せる」など)。商品の特性上、使用時に
  汚れ・角栓除去等の爽快感のある視覚的満足感(キモジョイ)を見せられる場合は、
  そのような使用シーンのカットも検討する。テロップの内容と矛盾しない画(え)に
  すること。
- "composition_prompt": 画角・構図・ライティングの雰囲気を表す英語の画像生成
  プロンプト。アングル(例: overhead, 45-degree, close-up)、画面構成、背景、
  光の当たり方を指定すること。実在のブランド名・ロゴ・パッケージの正確な
  形状や文字は一切書かないこと(参考画像は構図の例であり、実商品の外観を
  再現するものではないため)。

# 出力形式 (JSON厳守、他の文章は一切出力しない)
{
  "concept": "...",
  "shots": [
    {"caption": "...", "duration": 2.3, "shot_description": "...",
     "composition_prompt": "..."}
  ],
  "hashtags": ["...", "...", "..."]
}
shotsの最初の要素がフック、最後の要素がCTA、間が本文テロップ。
"""

SYSTEM_PROMPT = """\
あなたはTikTok Shop動画の構成作家です。入力された発話の文字起こしと商品情報から、
以下のルールに厳密に従って編集方針をJSONで出力してください。

# フック (冒頭3秒・新規追加するテロップ)
- 結論を言わない未完了状態にする(ツァイガルニク効果)、「まだ○○してる人」型の
  呼びかけにする(カクテルパーティ効果)、得られる未来を期待させる(報酬予測)、
  または二択で考えさせる(ダブルバインド)のいずれかにする。
- 数字は書かない。

# テロップ本文 (元の発話を整文したもの)
- 元の発話のフィラー(「えー」「あの」等)を除いて整文する。意味は変えない。
- 全角12〜16文字程度を目安にする。
- 元の発話に悩み→解決の順序(PAS)があれば、その順序を保持する。
- 元の発話に「どこで買えるか」「本当に効果があるか」「成分・対象肌質」など、
  視聴者が疑問・不信感を抱きやすい情報への言及があれば優先的に残す。
- 元の発話に使用時の爽快感・満足感を表す描写(角栓除去・汚れ落ち等)があれば、
  その質感は保持してよい(キモジョイ)。
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


def _gemini_client():
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEYが設定されていません。", file=sys.stderr)
        sys.exit(1)

    return genai.Client(api_key=api_key)


def call_gemini_highlight(segments, product_info):
    from google.genai import types

    client = _gemini_client()

    indexed = [{"index": i, **seg} for i, seg in enumerate(segments)]
    user_content = json.dumps(
        {"segments": indexed, "product_info": product_info},
        ensure_ascii=False,
    )

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=HIGHLIGHT_SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )

    result = json.loads(response.text)
    start_index = max(0, min(int(result["start_index"]), len(segments) - 1))
    end_index = max(start_index, min(int(result["end_index"]), len(segments) - 1))
    return start_index, end_index, result.get("reason", "")


def call_gemini_classify(manifest_items, product_info):
    from google.genai import types

    client = _gemini_client()

    parts = [json.dumps({"product_info": product_info,
                          "clip_count": len(manifest_items)}, ensure_ascii=False)]
    for i, item in enumerate(manifest_items):
        parts.append(f"=== clip_{i} ===")
        for frame in item["frames"]:
            frame_path = Path(frame)
            mime = "image/png" if frame_path.suffix.lower() == ".png" else "image/jpeg"
            parts.append(types.Part.from_bytes(data=frame_path.read_bytes(), mime_type=mime))

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=parts,
        config=types.GenerateContentConfig(
            system_instruction=CLASSIFY_SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )

    return json.loads(response.text)["results"]


def call_gemini_verify_shotlist(shots, manifest_items):
    from google.genai import types

    client = _gemini_client()

    shot_info = [{"index": i, "shot_description": s["shot_description"],
                  "caption": s["caption"]} for i, s in enumerate(shots)]
    parts = [json.dumps({"shots": shot_info}, ensure_ascii=False)]
    for i, item in enumerate(manifest_items):
        parts.append(f"=== shot_{i} ===")
        for frame in item["frames"]:
            frame_path = Path(frame)
            mime = "image/png" if frame_path.suffix.lower() == ".png" else "image/jpeg"
            parts.append(types.Part.from_bytes(data=frame_path.read_bytes(), mime_type=mime))

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=parts,
        config=types.GenerateContentConfig(
            system_instruction=VERIFY_SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )

    return json.loads(response.text)["results"]


def call_gemini_plan(product_info, available_clips):
    from google.genai import types

    client = _gemini_client()

    user_content = json.dumps(
        {"available_clips": available_clips, "product_info": product_info},
        ensure_ascii=False,
    )

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=PLAN_SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.7,
        ),
    )

    return json.loads(response.text)


def _extract_product_name(product_info):
    for line in product_info.splitlines():
        line = line.strip()
        for prefix in ("商品名:", "商品名："):
            if line.startswith(prefix):
                return line[len(prefix):].strip()
    return None


IMAGE_MODEL = "gemini-3.1-flash-image"
IMAGE_STYLE_SUFFIX = (
    ", clean minimal background, soft natural lighting, vertical 9:16 "
    "composition, no visible text, no logos, no brand names, generic "
    "product-mockup photo for composition reference only"
)


def call_gemini_image(composition_prompt):
    client = _gemini_client()

    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=composition_prompt + IMAGE_STYLE_SUFFIX,
    )

    for part in response.candidates[0].content.parts:
        if part.inline_data:
            return part.inline_data.data

    return None


def call_gemini_shotlist(product_info):
    from google.genai import types

    client = _gemini_client()

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=json.dumps({"product_info": product_info}, ensure_ascii=False),
        config=types.GenerateContentConfig(
            system_instruction=SHOTLIST_SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.7,
        ),
    )

    return json.loads(response.text)


def call_gemini_script(product_info):
    from google.genai import types

    client = _gemini_client()

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=json.dumps({"product_info": product_info}, ensure_ascii=False),
        config=types.GenerateContentConfig(
            system_instruction=SCRIPT_SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.7,
        ),
    )

    return json.loads(response.text)


def build_seg_from_script(plan):
    segments = []
    t = 0.0
    for item in [plan["hook"]] + plan["captions"] + [plan["cta"]]:
        dur = max(0.5, float(item["duration"]))
        segments.append({"start": t, "end": t + dur, "text": item["text"]})
        t += dur

    return {"segments": segments, "hashtags": plan["hashtags"]}


def call_gemini(segments, product_info):
    from google.genai import types

    client = _gemini_client()

    user_content = json.dumps(
        {"segments": segments, "product_info": product_info},
        ensure_ascii=False,
    )

    response = client.models.generate_content(
        model="gemini-3.8-flash",
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


IMAGES_PER_SHOT = 2
SHOT_LABELS = ("フック", "本文", "CTA")


def _shot_label(index, total):
    if index == 0:
        return "フック"
    if index == total - 1:
        return "CTA"
    return f"本文{index}"


def _render_shotlist_html(concept, shots, hashtags):
    import base64

    rows = []
    for i, shot in enumerate(shots):
        images_html = "".join(
            f'<img src="data:image/png;base64,{base64.b64encode(img).decode()}" '
            f'class="ref-img" alt="参考イメージ{j+1}">'
            for j, img in enumerate(shot.get("images", []))
            if img is not None
        )
        rows.append(f"""
        <section class="shot">
          <h2>カット{i + 1}（{_shot_label(i, len(shots))}） ー 目安{shot['duration']:.1f}秒</h2>
          <p class="desc"><strong>撮る内容:</strong> {shot['shot_description']}</p>
          <p class="caption"><strong>テロップ:</strong> 「{shot['caption']}」</p>
          <div class="refs">{images_html}</div>
          <p class="note">※参考イメージは構図・アングルの例です。実際の商品で撮影してください。</p>
        </section>
        """)

    hashtags_html = " ".join(f"#{h}" for h in hashtags)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>撮影指示書</title>
<style>
  body {{ font-family: -apple-system, 'Hiragino Sans', sans-serif; max-width: 720px;
         margin: 0 auto; padding: 24px; background: #faf9f7; color: #222; }}
  h1 {{ font-size: 1.4em; }}
  .concept {{ background: #fff3cd; padding: 12px 16px; border-radius: 8px; }}
  .shot {{ background: #fff; border-radius: 12px; padding: 16px; margin: 20px 0;
           box-shadow: 0 1px 4px rgba(0,0,0,0.1); }}
  .shot h2 {{ font-size: 1.1em; margin-top: 0; }}
  .caption {{ color: #c0392b; }}
  .refs {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .ref-img {{ width: 160px; border-radius: 8px; border: 1px solid #ddd; }}
  .note {{ font-size: 0.85em; color: #888; }}
  .hashtags {{ color: #555; margin-top: 24px; }}
</style>
</head>
<body>
<h1>撮影指示書</h1>
<p class="concept"><strong>企画:</strong> {concept}</p>
{"".join(rows)}
<p class="hashtags">{hashtags_html}</p>
</body>
</html>
"""


def main_shotlist():
    if len(sys.argv) != 4:
        print("usage: edit_brain.py shotlist product_info.txt outdir",
              file=sys.stderr)
        sys.exit(1)

    product_info_path, outdir_path = sys.argv[2:4]
    outdir = Path(outdir_path)
    images_dir = outdir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    with open(product_info_path, encoding="utf-8") as f:
        product_info = f.read().strip()

    plan = call_gemini_shotlist(product_info)
    shots = plan["shots"]

    for i, shot in enumerate(shots):
        images = []
        for j in range(IMAGES_PER_SHOT):
            img = call_gemini_image(shot["composition_prompt"])
            if img is not None:
                (images_dir / f"shot{i + 1}_{j + 1}.png").write_bytes(img)
            images.append(img)
        shot["images"] = images
        shot["image_files"] = [
            f"images/shot{i + 1}_{j + 1}.png" for j in range(IMAGES_PER_SHOT)
        ]
        print(f"[edit_brain] カット{i + 1} 参考イメージ{len(images)}枚生成")

    shotlist_json = {
        "concept": plan["concept"],
        "shots": [{k: v for k, v in s.items() if k != "images"} for s in shots],
        "hashtags": plan["hashtags"],
    }
    with open(outdir / "shotlist.json", "w", encoding="utf-8") as f:
        json.dump(shotlist_json, f, ensure_ascii=False, indent=2)

    html = _render_shotlist_html(plan["concept"], shots, plan["hashtags"])
    html_path = outdir / "撮影指示書.html"
    html_path.write_text(html, encoding="utf-8")

    print(f"[edit_brain] 企画: {plan['concept']} "
          f"({len(shots)}カット) -> {outdir / 'shotlist.json'}, {html_path}")


def main_script():
    if len(sys.argv) != 4:
        print("usage: edit_brain.py script product_info.txt seg_ai.json",
              file=sys.stderr)
        sys.exit(1)

    product_info_path, out_path = sys.argv[2:4]

    with open(product_info_path, encoding="utf-8") as f:
        product_info = f.read().strip()

    plan = call_gemini_script(product_info)
    seg_ai = build_seg_from_script(plan)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(seg_ai, f, ensure_ascii=False, indent=2)

    total = seg_ai["segments"][-1]["end"]
    print(f"[edit_brain] 台本生成(ナレーション無し素材用) 合計{total:.1f}秒 -> {out_path}")


def main_plan():
    if len(sys.argv) != 5:
        print("usage: edit_brain.py plan manifest.json product_info.txt plan.json",
              file=sys.stderr)
        sys.exit(1)

    manifest_path, product_info_path, out_path = sys.argv[2:5]

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    with open(product_info_path, encoding="utf-8") as f:
        product_info = f.read().strip()

    classified = call_gemini_classify(manifest, product_info)

    id_to_clip = {f"clip_{i}": item["clip"] for i, item in enumerate(manifest)}
    for c in classified:
        c["clip"] = id_to_clip.get(c["id"])

    target_product = _extract_product_name(product_info)
    if target_product:
        matched = [c for c in classified if target_product in (c.get("product") or "")]
    else:
        matched = [c for c in classified if (c.get("product") or "unknown") != "unknown"]

    if not matched:
        print("商品情報に一致するクリップが見つかりませんでした。", file=sys.stderr)
        print(f"分類結果: {json.dumps(classified, ensure_ascii=False)}", file=sys.stderr)
        sys.exit(1)

    print(f"[edit_brain] {len(manifest)}クリップ中{len(matched)}本が商品に一致 "
          f"(除外: {len(manifest) - len(matched)}本)")

    plan = call_gemini_plan(product_info, matched)

    id_to_item = {c["id"]: c for c in matched}
    segments = []
    t = 0.0
    for entry in plan["items"]:
        clip_info = id_to_item.get(entry["clip_id"])
        if clip_info is None:
            print(f"警告: 未知のclip_id '{entry['clip_id']}' を無視します。",
                  file=sys.stderr)
            continue
        dur = max(0.5, float(entry["duration"]))
        segments.append({"start": t, "end": t + dur, "text": entry["text"],
                          "clip": clip_info["clip"]})
        t += dur

    out = {"concept": plan["concept"], "segments": segments,
           "hashtags": plan["hashtags"]}

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[edit_brain] 企画: {plan['concept']} "
          f"({len(segments)}カット・合計{t:.1f}秒) -> {out_path}")


def main_verify():
    if len(sys.argv) != 5:
        print("usage: edit_brain.py verify shotlist.json manifest.json plan.json",
              file=sys.stderr)
        sys.exit(1)

    shotlist_path, manifest_path, out_path = sys.argv[2:5]

    with open(shotlist_path, encoding="utf-8") as f:
        shotlist = json.load(f)

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    shots = shotlist["shots"]
    if len(shots) != len(manifest):
        print(f"カット数({len(shots)})とアップロードされたクリップ数"
              f"({len(manifest)})が一致しません。shotlist.jsonのカット順と"
              f"同じ本数・同じ順番でクリップを用意してください。",
              file=sys.stderr)
        sys.exit(1)

    results = call_gemini_verify_shotlist(shots, manifest)

    segments = []
    t = 0.0
    mismatches = []
    for i, (shot, result) in enumerate(zip(shots, results)):
        dur = max(0.5, float(shot["duration"]))
        match = bool(result.get("match", True))
        segments.append({"start": t, "end": t + dur, "text": shot["caption"],
                          "clip": manifest[i]["clip"], "verified": match})
        if not match:
            mismatches.append((i + 1, result.get("note", "")))
        t += dur

    out = {"concept": shotlist["concept"], "segments": segments,
           "hashtags": shotlist["hashtags"]}

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    if mismatches:
        print(f"[edit_brain] 警告: {len(mismatches)}カットで指示と映像が "
              f"一致していない可能性があります。内容を確認してください:",
              file=sys.stderr)
        for idx, note in mismatches:
            print(f"  - カット{idx}: {note}", file=sys.stderr)

    print(f"[edit_brain] {len(segments)}カット・合計{t:.1f}秒 "
          f"(不一致疑い{len(mismatches)}件) -> {out_path}")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "script":
        main_script()
        return

    if len(sys.argv) >= 2 and sys.argv[1] == "plan":
        main_plan()
        return

    if len(sys.argv) >= 2 and sys.argv[1] == "shotlist":
        main_shotlist()
        return

    if len(sys.argv) >= 2 and sys.argv[1] == "verify":
        main_verify()
        return

    if len(sys.argv) != 5:
        print("usage: edit_brain.py seg.json product_info.txt "
              "seg_ai.json highlight.json\n"
              "       edit_brain.py script product_info.txt seg_ai.json\n"
              "       edit_brain.py plan manifest.json product_info.txt plan.json\n"
              "       edit_brain.py shotlist product_info.txt outdir\n"
              "       edit_brain.py verify shotlist.json manifest.json plan.json",
              file=sys.stderr)
        sys.exit(1)

    seg_path, product_info_path, out_path, highlight_path = sys.argv[1:5]

    with open(seg_path, encoding="utf-8") as f:
        segments = json.load(f)["segments"]

    with open(product_info_path, encoding="utf-8") as f:
        product_info = f.read().strip()

    start_index, end_index, reason = call_gemini_highlight(segments, product_info)
    highlight = segments[start_index:end_index + 1]

    with open(highlight_path, "w", encoding="utf-8") as f:
        json.dump({"start": highlight[0]["start"], "end": highlight[-1]["end"],
                   "reason": reason}, f, ensure_ascii=False, indent=2)

    offset = highlight[0]["start"]
    rebased = [{"start": s["start"] - offset, "end": s["end"] - offset,
                "text": s["text"]} for s in highlight]

    plan = call_gemini(rebased, product_info)
    seg_ai = build_seg_ai(rebased, plan)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(seg_ai, f, ensure_ascii=False, indent=2)

    print(f"[edit_brain] 区間[{start_index}:{end_index}] "
          f"({highlight[0]['start']:.1f}s-{highlight[-1]['end']:.1f}s) "
          f"hook_freeze={HOOK_DURATION} -> {out_path}, {highlight_path}")


if __name__ == "__main__":
    main()
