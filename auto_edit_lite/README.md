# auto_edit_lite — TikTok Shop 自動編集ツール (Phase1/2)

TikTok Shop向け動画の無音カット・文字起こし・字幕焼き込みを自動化するCLIツール群。

## 重要: 配布範囲の制約

`edit_brain.py` には非公開のAI判断プロンプト（`SYSTEM_PROMPT`）が含まれる。
**このファイルは素人スタッフへの配布物に含めないこと。** 配布するのは
`lite_edit.py` と、Gemini側で生成済みの `seg_ai.json` のような結果ファイルのみ。

## セットアップ（自宅Mac側で実行）

```bash
brew install ffmpeg
pip3 install --break-system-packages faster-whisper google-genai
```

Gemini APIキーの取得:

1. https://aistudio.google.com/apikey でAPIキーを発行
2. `~/.zshrc` に以下を追記して `source ~/.zshrc`

```bash
export GEMINI_API_KEY="取得したキー"
```

## 使い方

### Phase1単体（無音カット〜字幕焼き込みまで一括）

```bash
python3 lite_edit.py all 素材.mp4 out/
```

`out/final.mp4` に縦型(1080x1920)・単一スタイル字幕付きの動画が出力される。

個別ステップで実行する場合:

```bash
python3 lite_edit.py cut 素材.mp4 cut.mp4 -35 0.6
python3 lite_edit.py transcribe cut.mp4 seg.json
python3 lite_edit.py caption seg.json subs.ass
python3 lite_edit.py render cut.mp4 subs.ass final.mp4
```

### Phase1 → Phase2 連結（切り抜き区間の自動選定込み）

「大量動画素材_切り抜き用」のような**長尺の元素材**から、TikTok Shop投稿用に
最も訴求力のあるひと続きの区間（15〜30秒目安）をGeminiに選ばせ、その区間だけを
切り出してフック(冒頭)・整文テロップ・CTA(末尾)・ハッシュタグを生成する。
商品情報は1個のテキストファイルで渡す。

```bash
python3 lite_edit.py cut 素材.mp4 cut.mp4
python3 lite_edit.py transcribe cut.mp4 seg.json
python3 edit_brain.py seg.json product_info.txt seg_ai.json highlight.json
python3 lite_edit.py trim cut.mp4 highlight.json clip.mp4
python3 lite_edit.py caption seg_ai.json subs.ass
python3 lite_edit.py render clip.mp4 subs.ass final.mp4 --hook-freeze 2.3 --cta-freeze 2.3
```

- `edit_brain.py`はまずGeminiに全セグメントを渡し、最も訴求力のある連続区間
  (`start_index`〜`end_index`)を選ばせる。選んだ区間の実時間は`highlight.json`
  に`{"start": ..., "end": ..., "reason": "..."}`として出力される。
- 続けて、その区間だけに対してフック・整文テロップ・CTA・ハッシュタグを生成し
  `seg_ai.json`に出力する（区間の先頭を0秒として時刻を振り直し済み）。
- `lite_edit.py trim`は`highlight.json`の`start`/`end`で`cut.mp4`から
  その区間だけを切り出す（`cut`と同じく再エンコード方式）。
- `--hook-freeze`にはPhase2が先頭に追加したフックの秒数、`--cta-freeze`には
  末尾に追加したCTAの秒数（いずれも`edit_brain.py`の`HOOK_DURATION`、デフォルト
  2.3秒）を指定する。先頭/末尾をその秒数分だけ静止＋無音で延長し、テロップと
  映像の時間軸を同期させる。**`--cta-freeze`を指定し忘れると、CTAのテロップが
  表示しきる前に映像が終わってしまうので注意。**

区間選定を使わず、素材全体をそのまま編集したい場合（素材が既に短尺の場合など）は
`trim`を省略し、`caption`/`render`に`cut.mp4`をそのまま渡せばよい。

## 動作確認状況

- `cut` / `trim` / `transcribe` / `caption` / `render`（Phase1一連）、および
  `edit_brain.py`によるハイライト区間選定・Gemini API実呼び出しまで含め、
  クラウド開発環境で実際に動かしてエンドツーエンドで動作確認済み（合成音声の
  テスト素材、実際に取得したGemini APIキーを使用）。4つのパートに分けた
  テスト素材（前置き雑談/天気の話/商品の訴求/締めの挨拶）で試したところ、
  前置きと締めの挨拶を除外し、悩み提起から商品の効果までの核心部分だけを
  正しく選定できることを確認。
- 本物のTikTok Shop用に用意された実素材（Google Driveの`大量動画素材_切り抜き
  用_高画質`フォルダ、約30本）のうち1本（60秒・既存キャスト動画）でもPhase1の
  一連の動作を確認済み。ただし自宅Macの実環境（Apple Silicon等）では未検証。
  また、そのフォルダの素材は**既に字幕・商品オーバーレイが焼き込まれた
  動画**だったため、本ツールが追加するテロップと二重表示になる問題が
  あった。切り抜き元として使う素材が無編集のraw footageか、既存の編集済み
  動画かによって対応が変わるため、本番運用前に素材の性質を確認すること。
- Gemini側のモデルは`gemini-2.5-flash`が新規ユーザー向けには廃止されていた
  ため、`gemini-3.8-flash`に変更済み（2026年時点の最新モデル名。将来的に
  また変わる可能性があるため、エラーが出た場合は`edit_brain.py`の
  `call_gemini()`内のモデル名を確認すること）。
- faster-whisperが内部で使うPyAV(`av`パッケージ)はバージョンによっては
  `model.transcribe()`実行時に`TypeError: open() got an unexpected keyword
  argument 'metadata_errors'`のようなエラーで落ちることがある。本ツールは
  ffmpeg CLIで直接PCMにデコードしてnumpy配列を渡すことでPyAVの内部デコードを
  回避する実装にしてあるため、通常は影響を受けない。もし同様のエラーが出た
  場合は`pip3 show av`でバージョンを確認すること。

## 既知の制約

- 話者分けは未対応（単一話者前提）。
- 無音区間が無く非常に長い1セグメントになった場合、テロップが縦に5行以上
  など極端に長くなることがある（セーフゾーン下部からはみ出す可能性）。
  現状は句読点/スペース際での折り返しのみで、行数の上限や文字起こし
  セグメントの強制分割は行っていない。
- 本物のTikTok Shop素材・自宅Macの実環境では未検証。
