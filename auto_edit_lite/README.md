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

### Phase1 → Phase2 連結

Phase2はフック(冒頭)・整文テロップ・CTA(末尾)・ハッシュタグをAIで生成し、
`seg.json` を `seg_ai.json` に変換する。商品情報は1個のテキストファイルで渡す。

```bash
python3 lite_edit.py cut 素材.mp4 cut.mp4
python3 lite_edit.py transcribe cut.mp4 seg.json
python3 edit_brain.py seg.json product_info.txt seg_ai.json
python3 lite_edit.py caption seg_ai.json subs.ass
python3 lite_edit.py render cut.mp4 subs.ass final.mp4 --hook-freeze 2.3
```

`--hook-freeze` にはPhase2が追加したフックの秒数（`edit_brain.py` の
`HOOK_DURATION`、デフォルト2.3秒）を指定する。先頭をその秒数分だけ
静止＋無音にして、テロップと映像の時間軸を同期させる。

## 動作確認状況

- `cut` / `transcribe` / `caption` / `render`（Phase1一連）はクラウド開発環境で
  ffmpeg・faster-whisperを実際に動かして動作確認済み。ただし本物のTikTok Shop
  素材・自宅Macの実環境（Apple Silicon等）では未検証。
- `edit_brain.py`のGemini API呼び出しは未検証（APIキー未取得のため）。
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
