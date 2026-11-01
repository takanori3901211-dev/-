# Notta 文字起こし → Claude 議事録・タスクリスト自動生成

Nottaで文字起こしが完成したら自動でフックし、Claude APIで議事録とタスク
リストを生成、Google Workspace（Docs/Sheets）に保存してメールで通知する
パイプライン。出力先はチームがGoogle Workspaceのみを日常的に使っている
ことを踏まえて、新しいツールを増やさずGoogle Workspace内に閉じる構成にした。

## 全体の流れ

```
Notta（文字起こし完了）
  → Webhook通知
  → このサーバー（Cloud Run等にデプロイ）
      1. Notta APIで文字起こし本文を取得
      2. Claude API（claude-opus-5-5）で議事録（Markdown）とタスクリスト
         （担当者・タスク・期限のJSON）を生成
      3. 文字起こし本文・議事録をGoogle Driveの指定フォルダにGoogle Docsとして保存
      4. タスクリストを、タスク管理用の単一Google Sheetsに行として追記
         （会議をまたいで積み上がる一覧になる。完了列はSheets上で手動チェック）
      5. Gmailで議事録・タスクシートへのリンクを通知
         （見に行くのを忘れる、という前提に対応するため）
  → Claude Projectの「Google Drive連携」でそのフォルダをナレッジソースに
    指定しておくと、Project側に自動で反映される
```

## 重要な前提・制約（必ず最初に確認すること）

- **「Claude Projectのナレッジに直接APIで追加する」ことはできない。**
  claude.aiのProjectナレッジは現時点でAnthropicの公開APIから書き込む
  手段が無い（Developer APIはあくまでチャット補完のためのAPIで、
  claude.aiのProject機能とは別物）。実現可能な方法は、Claude Project
  の設定画面でGoogle Driveのフォルダをナレッジソースとして接続し、
  そのフォルダの内容が自動同期される、という間接的な経路。本実装は
  その前提で、保存先をGoogle Driveにしている。
- **Notta APIのエンドポイント仕様は未確認。** `app/notta_client.py` の
  ベースURL・パス（`https://api.notta.ai/v1/transcriptions/{id}/result`）
  は第三者の解説記事を参考にした推定であり、Notta公式のデベロッパー
  ドキュメント・ダッシュボードで実際の仕様（認証方式・エンドポイント・
  Webhookのペイロード形式）を確認し、必要なら修正すること。
- **Gmail通知はSMTP+アプリパスワード方式。** Workspace管理者権限が要る
  ドメイン全体の委任（Gmail APIでのなりすまし送信）は使わず、通知元の
  Googleアカウントで2段階認証を有効化してアプリパスワードを発行する方式
  にしている。管理者権限無しで設定できる代わりに、送信元アカウントの
  パスワードに準じた扱いの認証情報をサーバー側に保持することになる点は
  踏まえておくこと。
- **この開発環境にはNotta/Anthropic/Google Cloudの実アカウント・APIキーが
  無いため、実際のWebhook受信・API呼び出しは未テスト。** 構文・import
  チェックのみ実施済み。

## セットアップ

### 1. 必要な認証情報を揃える

| 項目 | 入手元 |
|---|---|
| `NOTTA_API_KEY` | Nottaのダッシュボード（API/Webhookが使える有料プランで発行） |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/ |
| Google サービスアカウントJSON | Google Cloud Console → IAMと管理 → サービスアカウント。Drive APIとSheets APIを有効化し、保存先フォルダとタスクシートをそのサービスアカウントのメールアドレスに共有（編集者権限）しておく |
| `DRIVE_FOLDER_ID` | 保存先Google DriveフォルダのURLに含まれるID |
| `TASK_SHEET_ID` | タスク管理用に事前作成したGoogle SheetsのURLに含まれるID。1行目に `日付 / 会議名 / 担当者 / タスク / 期限 / 完了` のヘッダーを入れておく |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | 通知を送るGoogleアカウントで2段階認証を有効化し、アカウント設定の「アプリパスワード」で発行 |
| `NOTIFY_EMAIL_TO` | 通知を受け取りたいメールアドレス |

`.env.example` を `.env` にコピーして値を埋める。

### 2. ローカルで動作確認（構文・起動確認のみ）

```bash
pip install -r requirements.txt
python -m app.main
```

`http://localhost:8080/healthz` が `{"status": "ok"}` を返せば起動は成功。
Webhook受信からの一連の処理は実際のNotta/Anthropic/Googleの認証情報が
無いとテストできない。

### 3. Cloud Runへデプロイ（例）

```bash
gcloud run deploy notta-minutes-bot \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars NOTTA_API_KEY=xxx,ANTHROPIC_API_KEY=xxx,DRIVE_FOLDER_ID=xxx \
  --set-secrets GOOGLE_SERVICE_ACCOUNT_JSON=/secrets/sa.json=notta-bot-sa:latest
```

サービスアカウントJSONはSecret Managerに登録してマウントする想定
（上記はその一例。環境に合わせて調整が必要）。

### 4. NottaのWebhook設定

デプロイ後に得られるURL（例: `https://notta-minutes-bot-xxxx.a.run.app/webhook/notta`）
を、NottaのWebhook設定画面で「Transcription Completed」イベントの宛先
として登録する。簡易的な保護として `INBOUND_WEBHOOK_SHARED_SECRET` を
設定した場合は、URLに `?secret=...` を付与して登録する。

### 5. Claude Project側の設定（一度だけ）

claude.aiのProject設定からGoogle Drive連携を有効化し、上記 `DRIVE_FOLDER_ID`
のフォルダをナレッジソースとして追加する。これで新しい文字起こし・議事録
ファイルが自動的にProjectのナレッジに反映される（同期タイミングはClaude
側の仕様に依存）。

## 次に決めること

- Notta API/Webhookの正式な仕様確認（エンドポイント・認証方式・
  ペイロード形式）。
- タスクシートの「完了」列をどう運用するか（手動チェックのみで十分か、
  将来的に通知や集計を増やすか）。
