# TikTok Shop 自動編集ツール

編集未経験のスタッフでも素材を出すだけで一定品質の編集済み動画が自動生成される
仕組みを目指すプロジェクト。詳細は [`HANDOFF.md`](./HANDOFF.md) を参照。

実装は [`auto_edit_lite/`](./auto_edit_lite/) 配下にある
（セットアップ: [`auto_edit_lite/README.md`](./auto_edit_lite/README.md)、
仕様: [`auto_edit_lite/仕様書.md`](./auto_edit_lite/仕様書.md)）。

## 重要

`auto_edit_lite/edit_brain.py` には非公開のAI判断プロンプトが含まれる。
素人ユーザーへの配布物には含めないこと（詳細は`HANDOFF.md`参照）。

## その他のツール

[`casting_research/`](./casting_research/) — X上で伸びている商品の切り抜きから
タレント/インフルエンサーのキャスティング事例を収集・記録・集計するリサーチ
ツール。詳細は[`casting_research/README.md`](./casting_research/README.md)参照。
