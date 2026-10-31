#!/usr/bin/env python3
"""1コマンドで商品情報+素材から編集済み動画を作る統合スクリプト。

内部ではlite_edit.py/edit_brain.pyの既存コマンドを順番に呼び出すだけで、
新しい編集ロジックは持たない(個別に検証済みの部品を繋ぐだけ)。

使い方:
  長尺・ナレーションあり素材1本から作る場合:
    python3 make_video.py 商品情報.txt 素材.mp4 out/

  ナレーション無しB-rollクリップ複数本から作る場合(商品混在OK、Visionで
  自動選別・企画提案される):
    python3 make_video.py 商品情報.txt clip1.mp4 clip2.mp4 ... out/

GEMINI_API_KEY環境変数が必須。
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LITE_EDIT = HERE / "lite_edit.py"
EDIT_BRAIN = HERE / "edit_brain.py"


def run(cmd):
    cmd = [str(c) for c in cmd]
    print("$ " + " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print(f"[make_video] コマンドが失敗しました: {' '.join(cmd)}",
              file=sys.stderr)
        sys.exit(r.returncode)


def make_from_long_video(product_info, src, outdir):
    cut = outdir / "cut.mp4"
    seg = outdir / "seg.json"

    run(["python3", LITE_EDIT, "cut", src, cut])
    run(["python3", LITE_EDIT, "transcribe", cut, seg])

    segments = json.loads(seg.read_text(encoding="utf-8"))["segments"]
    if not segments:
        print("[make_video] 発話が検出されませんでした(ナレーション無し素材の"
              "ようです)。複数のB-rollクリップを入力として渡してください。",
              file=sys.stderr)
        sys.exit(1)

    seg_ai = outdir / "seg_ai.json"
    highlight = outdir / "highlight.json"
    clip = outdir / "clip.mp4"
    subs = outdir / "subs.ass"
    final = outdir / "final.mp4"

    run(["python3", EDIT_BRAIN, seg, product_info, seg_ai, highlight])
    run(["python3", LITE_EDIT, "trim", cut, highlight, clip])
    run(["python3", LITE_EDIT, "caption", seg_ai, subs])
    run(["python3", LITE_EDIT, "render", clip, subs, final,
         "--hook-freeze", "2.3", "--cta-freeze", "2.3"])

    return final


def make_from_broll_clips(product_info, clips, outdir):
    frames_dir = outdir / "frames"
    plan = outdir / "plan.json"
    assembled = outdir / "assembled.mp4"
    subs = outdir / "subs.ass"
    final = outdir / "final.mp4"

    run(["python3", LITE_EDIT, "frames", frames_dir, "--clips", *clips])
    run(["python3", EDIT_BRAIN, "plan", frames_dir / "manifest.json",
         product_info, plan])
    run(["python3", LITE_EDIT, "assemble", plan, assembled])
    run(["python3", LITE_EDIT, "caption", plan, subs])
    run(["python3", LITE_EDIT, "render", assembled, subs, final])

    return final


def main():
    if len(sys.argv) < 4:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    product_info = sys.argv[1]
    outdir = Path(sys.argv[-1])
    inputs = sys.argv[2:-1]
    outdir.mkdir(parents=True, exist_ok=True)

    if len(inputs) == 1:
        final = make_from_long_video(product_info, inputs[0], outdir)
    else:
        final = make_from_broll_clips(product_info, inputs, outdir)

    print(f"[make_video] 完了 -> {final}")


if __name__ == "__main__":
    main()
