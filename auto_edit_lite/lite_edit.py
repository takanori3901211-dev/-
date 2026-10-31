#!/usr/bin/env python3
"""Phase1: ローカル試作 自動編集CLI (無音カット / 文字起こし / 字幕生成 / 書き出し)."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

VIDEO_W = 1080
VIDEO_H = 1920

SILENCE_MARGIN = 0.15
MIN_GAP = 0.3


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def _ffprobe_duration(path):
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(r.stdout.strip())


def _detect_silence(path, threshold_db, min_silence_duration):
    cmd = ["ffmpeg", "-i", str(path), "-af",
           f"silencedetect=noise={threshold_db}dB:d={min_silence_duration}",
           "-f", "null", "-"]
    r = _run(cmd)
    starts, ends = [], []
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start:\s*([\d.]+)", line)
        if m:
            starts.append(float(m.group(1)))
        m = re.search(r"silence_end:\s*([\d.]+)", line)
        if m:
            ends.append(float(m.group(1)))
    return list(zip(starts, ends))


def _speech_segments(duration, silences):
    """無音区間の補集合（発話区間）を、マージンと短い隙間の結合込みで作る。"""
    speech = []
    cursor = 0.0
    for s_start, s_end in silences:
        seg_start = cursor
        seg_end = min(s_start + SILENCE_MARGIN, duration)
        if seg_end > seg_start:
            speech.append([seg_start, seg_end])
        cursor = max(s_end - SILENCE_MARGIN, seg_end)
    if cursor < duration:
        speech.append([cursor, duration])

    merged = []
    for seg in speech:
        if merged and seg[0] - merged[-1][1] < MIN_GAP:
            merged[-1][1] = seg[1]
        else:
            merged.append(seg)
    return [tuple(s) for s in merged if s[1] - s[0] > 0.01]


def cmd_cut(args):
    duration = _ffprobe_duration(args.input)
    silences = _detect_silence(args.input, args.threshold_db, args.min_silence)
    segments = _speech_segments(duration, silences)

    if not segments:
        print("発話区間が検出できませんでした。閾値を調整してください。", file=sys.stderr)
        sys.exit(1)

    tmpdir = Path(args.output).parent / f".{Path(args.output).stem}_parts"
    tmpdir.mkdir(parents=True, exist_ok=True)
    list_path = tmpdir / "concat.txt"

    with open(list_path, "w") as f:
        for i, (start, end) in enumerate(segments):
            part = tmpdir / f"part_{i:04d}.mp4"
            # 短い区間だと直前のキーフレームしか無く -c copy で動画トラックが
            # 丸ごと欠落することがあるため、各区間は再エンコードして切り出す。
            _run(["ffmpeg", "-y", "-i", str(args.input), "-ss", str(start),
                  "-to", str(end), "-c:v", "libx264", "-preset", "fast",
                  "-c:a", "aac", str(part)])
            f.write(f"file '{part.resolve()}'\n")

    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
          "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", str(args.output)])

    print(f"[cut] {len(segments)}個の発話区間を結合 -> {args.output}")


def cmd_trim(args):
    with open(args.highlight, encoding="utf-8") as f:
        highlight = json.load(f)

    start, end = highlight["start"], highlight["end"]
    _run(["ffmpeg", "-y", "-i", str(args.input), "-ss", str(start),
          "-to", str(end), "-c:v", "libx264", "-preset", "fast",
          "-c:a", "aac", str(args.output)])

    print(f"[trim] {start:.1f}s-{end:.1f}s -> {args.output}")


def _allocate_durations(target_total, available):
    """targetを人数分で均等割りし、短いクリップの余りを他のクリップに
    再配分する(water-filling)。availableは各クリップの実尺のリスト。"""
    n = len(available)
    allocated = [0.0] * n
    remaining_total = target_total
    active = set(range(n))

    while active and remaining_total > 1e-6:
        share = remaining_total / len(active)
        progressed = False
        for i in list(active):
            room = available[i] - allocated[i]
            if room <= share + 1e-6:
                allocated[i] += room
                remaining_total -= room
                active.discard(i)
                progressed = True
        if not progressed:
            for i in active:
                allocated[i] += share
            remaining_total = 0.0
            break

    return allocated


def cmd_broll(args):
    """ナレーション無しのB-rollクリップ群を、目標秒数分だけ結合する。

    各クリップの実尺を上限に、短いクリップで埋まらなかった分は他のクリップ
    (特に長いクリップ)に再配分して、できるだけ目標秒数に近づける。
    """
    clips = list(args.clips)
    if not clips:
        print("B-rollクリップが指定されていません。", file=sys.stderr)
        sys.exit(1)

    available = [_ffprobe_duration(c) for c in clips]
    allocated = _allocate_durations(args.target_duration, available)

    tmpdir = Path(args.output).parent / f".{Path(args.output).stem}_broll_parts"
    tmpdir.mkdir(parents=True, exist_ok=True)
    list_path = tmpdir / "concat.txt"

    vf = (f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,"
          f"crop={VIDEO_W}:{VIDEO_H},setsar=1")

    with open(list_path, "w") as f:
        for i, (clip, dur) in enumerate(zip(clips, allocated)):
            if dur <= 0.05:
                continue
            part = tmpdir / f"part_{i:04d}.mp4"
            _run(["ffmpeg", "-y", "-i", str(clip), "-t", str(dur),
                  "-vf", vf, "-c:v", "libx264", "-preset", "fast",
                  "-c:a", "aac", "-ar", "44100", "-ac", "1", str(part)])
            f.write(f"file '{part.resolve()}'\n")

    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
          "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", str(args.output)])

    total = sum(allocated)
    print(f"[broll] {len(clips)}クリップを結合(合計{total:.1f}秒) -> {args.output}")


FRAME_SAMPLE_POINTS = (0.15, 0.5, 0.85)  # クリップ長に対する割合


def cmd_frames(args):
    """各クリップから複数の代表フレーム(クリップ長の15%/50%/85%地点)を抽出し、
    edit_brain.py planに渡すmanifest.jsonを作る。

    1フレームだけだと、たまたまブランド名/商品名が写っていない瞬間を
    拾ってしまい、AIによる商品分類の精度が落ちることがあるため複数枚にする。
    """
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for clip in args.clips:
        clip_path = Path(clip)
        dur = _ffprobe_duration(clip_path)
        frame_paths = []
        for i, ratio in enumerate(FRAME_SAMPLE_POINTS):
            ts = max(0.0, min(dur * ratio, max(dur - 0.05, 0.0)))
            frame_path = outdir / f"{clip_path.stem}_{i}.png"
            _run(["ffmpeg", "-y", "-i", str(clip_path), "-ss", str(ts),
                  "-frames:v", "1", str(frame_path)])
            frame_paths.append(str(frame_path.resolve()))
        manifest.append({"clip": str(clip_path.resolve()), "frames": frame_paths})

    manifest_path = outdir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"[frames] {len(manifest)}クリップ x {len(FRAME_SAMPLE_POINTS)}フレーム -> {manifest_path}")


def cmd_assemble(args):
    """plan.jsonのセグメントに従い、各セグメントが参照するクリップを
    割り当てられた秒数ぴったりに切り出して結合する(足りない分は末尾を
    静止させて延長)。"""
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)

    segments = plan["segments"]
    if not segments:
        print("plan.jsonにsegmentsがありません。", file=sys.stderr)
        sys.exit(1)

    tmpdir = Path(args.output).parent / f".{Path(args.output).stem}_assemble_parts"
    tmpdir.mkdir(parents=True, exist_ok=True)
    list_path = tmpdir / "concat.txt"

    vf_base = (f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,"
               f"crop={VIDEO_W}:{VIDEO_H},setsar=1")

    with open(list_path, "w") as f:
        for i, seg in enumerate(segments):
            clip = seg["clip"]
            dur = seg["end"] - seg["start"]
            avail = _ffprobe_duration(clip)
            part = tmpdir / f"part_{i:04d}.mp4"

            if avail >= dur:
                _run(["ffmpeg", "-y", "-i", str(clip), "-t", str(dur),
                      "-vf", vf_base, "-c:v", "libx264", "-preset", "fast",
                      "-c:a", "aac", "-ar", "44100", "-ac", "1", str(part)])
            else:
                pad = dur - avail
                vf = f"{vf_base},tpad=stop_duration={pad}:stop_mode=clone"
                _run(["ffmpeg", "-y", "-i", str(clip),
                      "-vf", vf, "-af", f"apad=pad_dur={pad}",
                      "-c:v", "libx264", "-preset", "fast",
                      "-c:a", "aac", "-ar", "44100", "-ac", "1", str(part)])

            f.write(f"file '{part.resolve()}'\n")

    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
          "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", str(args.output)])

    total = segments[-1]["end"]
    print(f"[assemble] {len(segments)}カット・合計{total:.1f}秒 -> {args.output}")


def _decode_audio_16k_mono(path):
    """ffmpegで直接PCMにデコードしてnumpy配列で返す。

    faster-whisperの内部デコード(PyAV)はインストールされたPyAVの
    バージョンによってAPIが変わり落ちることがあるため、ここでは
    ffmpeg CLIで直接デコードしてPyAVを経由しない。
    """
    import numpy as np

    cmd = ["ffmpeg", "-i", str(path), "-f", "s16le", "-ac", "1",
           "-ar", "16000", "-v", "error", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="ignore"))
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def cmd_transcribe(args):
    from faster_whisper import WhisperModel

    audio = _decode_audio_16k_mono(args.input)

    model = WhisperModel("small", device="cpu", compute_type="int8")
    kwargs = {}
    if getattr(args, "hotwords", None):
        kwargs["hotwords"] = args.hotwords
    segments_iter, _info = model.transcribe(
        audio, language="ja", vad_filter=True, **kwargs)

    segments = [
        {"start": s.start, "end": s.end, "text": s.text.strip()}
        for s in segments_iter
    ]

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"segments": segments}, f, ensure_ascii=False, indent=2)

    print(f"[transcribe] {len(segments)}セグメント -> {args.output}")


_BREAK_CHARS = "、。！？ "


def _split_once(text, max_chars):
    """textの先頭からmax_chars付近で1回だけ句読点/スペース際で切る。"""
    if len(text) <= max_chars:
        return text, ""

    best = None
    for offset in range(0, max_chars + 1):
        pos = max_chars - offset
        if 0 < pos < len(text) and text[pos - 1] in _BREAK_CHARS:
            best = pos
            break

    if best is None:
        best = max_chars

    return text[:best], text[best:]


def _wrap(text, max_chars=14):
    """画面幅に収まるよう、必要な行数分だけ句読点/スペース際で折り返す。"""
    text = text.strip()
    lines = []
    remaining = text
    while remaining:
        line, remaining = _split_once(remaining, max_chars)
        lines.append(line)

    return r"\N".join(lines)


def _ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    cs = int(round((s - int(s)) * 100))
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {VIDEO_W}
PlayResY: {VIDEO_H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Noto Sans CJK JP Black,76,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,4,0,2,60,60,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def cmd_caption(args):
    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    lines = [ASS_HEADER]
    for seg in data["segments"]:
        text = _wrap(seg["text"])
        start = _ass_time(seg["start"])
        end = _ass_time(seg["end"])
        lines.append(f"Dialogue: 0,{start},{end},Caption,,0,0,0,,{text}\n")

    with open(args.output, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"[caption] {len(data['segments'])}行 -> {args.output}")


def cmd_render(args):
    vf = (f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,"
          f"crop={VIDEO_W}:{VIDEO_H},setsar=1")

    af = "loudnorm=I=-14:TP=-1.0:LRA=11"

    # tpadはstart/stopを別々のフィルタインスタンスとして連結すると
    # stop側のパディング長が正しく計算されないため、1つのtpad呼び出しに
    # start_duration/stop_durationをまとめて指定する。
    tpad_opts = []
    if args.hook_freeze and args.hook_freeze > 0:
        tpad_opts.append(f"start_duration={args.hook_freeze}:start_mode=clone")
        af = f"adelay={int(args.hook_freeze * 1000)}|{int(args.hook_freeze * 1000)},{af}"
    if args.cta_freeze and args.cta_freeze > 0:
        tpad_opts.append(f"stop_duration={args.cta_freeze}:stop_mode=clone")
        af = f"{af},apad=pad_dur={args.cta_freeze}"

    if tpad_opts:
        vf = f"{vf},tpad={':'.join(tpad_opts)}"

    vf = f"{vf},ass={args.subs}"

    cmd = ["ffmpeg", "-y", "-i", str(args.input), "-vf", vf, "-af", af,
           "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-c:a", "aac", "-b:a", "192k", str(args.output)]
    r = _run(cmd)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit(1)

    print(f"[render] -> {args.output}")


def cmd_all(args):
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    cut_path = outdir / "cut.mp4"
    seg_path = outdir / "seg.json"
    ass_path = outdir / "subs.ass"
    final_path = outdir / "final.mp4"

    cmd_cut(argparse.Namespace(input=args.input, output=cut_path,
                                threshold_db=args.threshold_db,
                                min_silence=args.min_silence))
    cmd_transcribe(argparse.Namespace(input=cut_path, output=seg_path))
    cmd_caption(argparse.Namespace(input=seg_path, output=ass_path))
    cmd_render(argparse.Namespace(input=cut_path, subs=ass_path,
                                   output=final_path, hook_freeze=0,
                                   cta_freeze=0))

    print(f"[all] 完了 -> {final_path}")


def build_parser():
    p = argparse.ArgumentParser(description="TikTok Shop 自動編集 Phase1 CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("cut", help="無音カット")
    sp.add_argument("input")
    sp.add_argument("output")
    sp.add_argument("threshold_db", nargs="?", type=float, default=-35.0)
    sp.add_argument("min_silence", nargs="?", type=float, default=0.6)
    sp.set_defaults(func=cmd_cut)

    sp = sub.add_parser("trim", help="highlight.jsonの区間でcut.mp4を切り出す")
    sp.add_argument("input")
    sp.add_argument("highlight")
    sp.add_argument("output")
    sp.set_defaults(func=cmd_trim)

    sp = sub.add_parser("broll", help="ナレーション無しB-rollクリップ群を目標秒数で結合")
    sp.add_argument("output")
    sp.add_argument("--target-duration", type=float, required=True)
    sp.add_argument("--clips", nargs="+", required=True)
    sp.set_defaults(func=cmd_broll)

    sp = sub.add_parser("frames", help="各クリップの代表フレームを抽出しmanifest.jsonを作る")
    sp.add_argument("outdir")
    sp.add_argument("--clips", nargs="+", required=True)
    sp.set_defaults(func=cmd_frames)

    sp = sub.add_parser("assemble", help="企画(plan.json)に従ってクリップを結合する")
    sp.add_argument("plan")
    sp.add_argument("output")
    sp.set_defaults(func=cmd_assemble)

    sp = sub.add_parser("transcribe", help="文字起こし")
    sp.add_argument("input")
    sp.add_argument("output")
    sp.add_argument("--hotwords", default=None,
                     help="ブランド名・商品名など誤認識させたくない固有名詞を"
                          "スペース区切りで渡す(faster-whisperのhotwordsに渡る)")
    sp.set_defaults(func=cmd_transcribe)

    sp = sub.add_parser("caption", help="字幕(ASS)生成")
    sp.add_argument("input")
    sp.add_argument("output")
    sp.set_defaults(func=cmd_caption)

    sp = sub.add_parser("render", help="縦型書き出し+字幕焼き込み")
    sp.add_argument("input")
    sp.add_argument("subs")
    sp.add_argument("output")
    sp.add_argument("--hook-freeze", type=float, default=0.0,
                     help="Phase2で先頭に追加したフック秒数分、映像を静止+無音にする")
    sp.add_argument("--cta-freeze", type=float, default=0.0,
                     help="Phase2で末尾に追加したCTA秒数分、映像を静止+無音で延長する")
    sp.set_defaults(func=cmd_render)

    sp = sub.add_parser("all", help="cut->transcribe->caption->renderを一括実行")
    sp.add_argument("input")
    sp.add_argument("outdir")
    sp.add_argument("--threshold-db", type=float, default=-35.0)
    sp.add_argument("--min-silence", type=float, default=0.6)
    sp.set_defaults(func=cmd_all)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
