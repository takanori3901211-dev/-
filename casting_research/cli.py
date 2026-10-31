#!/usr/bin/env python3
"""キャスティングリサーチ記録用CLI。

WebSearch等で見つけた「商品を使っている切り抜き」と、そこに出演する
タレント/インフルエンサーの情報を構造化データとして記録する。
検索そのものはこのツールは行わない（手順はREADME.md参照）。
"""
from __future__ import annotations

import argparse
import sys

import store
from models import (
    ClipEntry,
    TalentEntry,
    HOOK_PATTERN_SUGGESTIONS,
    PLATFORM_CHOICES,
    SOURCE_METHOD_CHOICES,
)


def cmd_add_talent(args: argparse.Namespace) -> None:
    talents = store.load_talents()
    existing = store.find_talent_by_name(talents, args.name)
    if existing:
        existing.update(
            {k: v for k, v in {
                "x_handle": args.x,
                "tiktok_handle": args.tiktok,
                "instagram_handle": args.instagram,
                "youtube_handle": args.youtube,
                "genre": args.genre,
                "note": args.note,
            }.items() if v}
        )
        store.save_talents(talents)
        print(f"更新しました: {existing['id']} {existing['name']}")
        return

    entry = TalentEntry(
        id=store.next_id(talents, "t"),
        name=args.name,
        x_handle=args.x or "",
        tiktok_handle=args.tiktok or "",
        instagram_handle=args.instagram or "",
        youtube_handle=args.youtube or "",
        genre=args.genre or "",
        note=args.note or "",
    )
    talents.append(entry.to_dict())
    store.save_talents(talents)
    print(f"追加しました: {entry.id} {entry.name}")


def cmd_add_clip(args: argparse.Namespace) -> None:
    clips = store.load_clips()
    talents = store.load_talents()

    if not store.find_talent_by_name(talents, args.talent):
        print(
            f"注意: タレント「{args.talent}」は talents.json に未登録です。"
            f" add-talent で先に登録しておくと情報が紐づきます。",
            file=sys.stderr,
        )

    entry = ClipEntry(
        id=store.next_id(clips, "c"),
        product_name=args.product,
        talent_name=args.talent,
        clip_url=args.url,
        brand=args.brand or "",
        talent_handle=args.handle or "",
        platform_origin=args.platform,
        content_type=args.content_type or "",
        hook_pattern=args.hook or [],
        engagement_note=args.engagement or "",
        source_method=args.source,
        note=args.note or "",
    )
    clips.append(entry.to_dict())
    store.save_clips(clips)
    print(f"追加しました: {entry.id} {entry.product_name} / {entry.talent_name}")


def cmd_list_clips(args: argparse.Namespace) -> None:
    clips = store.load_clips()
    if args.product:
        clips = [c for c in clips if args.product in c["product_name"]]
    if args.talent:
        clips = [c for c in clips if args.talent in c["talent_name"]]
    if not clips:
        print("該当する事例はありません。")
        return
    for c in clips:
        print(
            f"[{c['id']}] {c['discovered_at']} "
            f"{c['product_name']} / {c['talent_name']} "
            f"({c['content_type'] or '-'}) {c['clip_url']}"
        )


def cmd_list_talents(args: argparse.Namespace) -> None:
    talents = store.load_talents()
    if not talents:
        print("タレントは未登録です。")
        return
    for t in talents:
        handles = ", ".join(
            h for h in [
                f"X:{t['x_handle']}" if t["x_handle"] else "",
                f"TikTok:{t['tiktok_handle']}" if t["tiktok_handle"] else "",
                f"IG:{t['instagram_handle']}" if t["instagram_handle"] else "",
                f"YT:{t['youtube_handle']}" if t["youtube_handle"] else "",
            ] if h
        )
        print(f"[{t['id']}] {t['name']} ({t['genre'] or '-'}) {handles}")


def cmd_report(args: argparse.Namespace) -> None:
    import report
    path = report.generate(output_dir=args.out)
    print(f"レポートを出力しました: {path}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    pt = sub.add_parser("add-talent", help="タレント/インフルエンサーを登録・更新")
    pt.add_argument("--name", required=True)
    pt.add_argument("--x", help="X(Twitter)ハンドル")
    pt.add_argument("--tiktok", help="TikTokハンドル")
    pt.add_argument("--instagram", help="Instagramハンドル")
    pt.add_argument("--youtube", help="YouTubeチャンネル")
    pt.add_argument("--genre", help="タレント/芸人/モデル/インフルエンサー等")
    pt.add_argument("--note")
    pt.set_defaults(func=cmd_add_talent)

    pc = sub.add_parser("add-clip", help="商品使用シーンの切り抜き事例を登録")
    pc.add_argument("--product", required=True, help="商品名")
    pc.add_argument("--talent", required=True, help="出演タレント名")
    pc.add_argument("--url", required=True, help="切り抜きポストのURL")
    pc.add_argument("--brand", help="ブランド名")
    pc.add_argument("--handle", help="タレントのX等ハンドル（任意）")
    pc.add_argument(
        "--platform", default="X", choices=PLATFORM_CHOICES,
        help="切り抜き元の元コンテンツが上がっていたプラットフォーム",
    )
    pc.add_argument("--content-type", help="例: バラエティ出演シーンの切り抜き")
    pc.add_argument(
        "--hook", action="append",
        help=f"伸びた要因タグ（複数指定可、自由記述可）。候補: {', '.join(HOOK_PATTERN_SUGGESTIONS)}",
    )
    pc.add_argument("--engagement", help="いいね数/再生数などのメモ")
    pc.add_argument(
        "--source", default="web_search", choices=SOURCE_METHOD_CHOICES,
        help="どうやって見つけたか",
    )
    pc.add_argument("--note")
    pc.set_defaults(func=cmd_add_clip)

    pl = sub.add_parser("list-clips", help="登録済みの切り抜き事例一覧")
    pl.add_argument("--product")
    pl.add_argument("--talent")
    pl.set_defaults(func=cmd_list_clips)

    plt = sub.add_parser("list-talents", help="登録済みタレント一覧")
    plt.set_defaults(func=cmd_list_talents)

    pr = sub.add_parser("report", help="集計レポート(Markdown)を生成")
    pr.add_argument("--out", default=None, help="出力先ディレクトリ")
    pr.set_defaults(func=cmd_report)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
