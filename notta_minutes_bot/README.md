# Notta 文字起こし → Claude 議事録・タスクリスト自動生成

Nottaで文字起こしした内容をClaude APIで議事録・タスクリストに整形し、
Google Workspace（Docs/Sheets）に保存してメールで通知するパイプライン。

Notta自体には開発者向けの公開API/Webhookが無い（後述）ため、**Notion を
中継点**にしている。Notta公式の「Notionへ送信」エクスポート機能（全プラン
利用可・手動）でNotionに溜め、そこから先（本文取得〜議事録生成〜保存〜通知）
を完全自動化する構成。

## 全体の流れ

```
① 会議後、Nottaの「Notionへ送信」機能で文字起こしをエクスポート
   （手動・1クリック。ここだけは自動化できない。詳細は下記「制約」参照）
       ↓
② Notion上の文字起こしデータベースに新しいページができる
       ↓
③ このサーバー（Cloud Run等）がCloud Scheduler等から定期的に /poll を
   呼ばれ、Notion APIで「処理済み」チェックがOFFのページを検索
       ↓
④ ページ本文をNotion APIで取得
       ↓
⑤ Claude API（claude-opus-5-5）で議事録（Markdown）とタスクリスト
   （担当者・タスク・期限のJSON）を生成
       ↓
⑥ 議事録＋文字起こし全文を1つのGoogle Docsにまとめて、Google Driveの
   指定フォルダに保存。タスクリストはタスク管理用の単一Google Sheetsに
   行として追記
       ↓
⑦ Gmailで議事録・タスクシートへのリンクを通知
       ↓
⑧ Notion側のページを「処理済み」にチェックして完了
```

Claude Projectの「Google Drive連携」で④の保存先フォルダをナレッジソース
として指定しておくと、Project側のナレッジにも自動反映される。

## 重要な前提・制約（必ず最初に確認すること）

- **NottaからNotionへのエクスポートは手動（1クリック）。** Notta公式の
  Notion連携は「会議終了後にNotionへ送信ボタンを押す」という per-meeting
  のエクスポート機能で、新しい文字起こしを自動でNotionに同期する機能では
  ない（2026年時点の公式ページの記載に基づく）。つまりこのシステムは
  「完全自動」ではなく、Notta→Notionのところだけ毎回ひと手間かかる。
  これが許容できない場合、Notta公式のMCP/CLI（`@notta-labs/notta-mcp` /
  `@notta-labs/notta-cli`。2026年9月リリース、全プラン対応）経由でNottaから
  直接自動取得する構成への切り替えを検討する。ただしCLIの認証
  （`notta auth setup`）はブラウザOAuthで、ヘッドレスサーバーでの非対話
  認証方法が公式ドキュメントで確認できていないため、Nottaサポートへの
  確認が別途必要。
- **NottaにはNotta自身が提供する公開REST API/Webhookは無いとみられる。**
  第三者のレビューサイト（GetApp）のFAQで明確に否定されており、公式の
  価格ページにもAPI/Webhookの記載が無い。そのためこの実装ではNottaの
  APIを直接呼ばず、公式のNotion連携を経由する構成にしている。
- **Notionのブロック構造は未確認。** `app/notion_client.py` の
  `fetch_page_text` は、Nottaがエクスポートしたページがparagraph/heading/
  list item等の素直なテキストブロックで構成されていることを前提にした
  簡易実装。実際にエクスポートしたページを見て、ネストしたブロックや
  テーブル等が使われている場合は取得ロジックを調整すること。
- **「Claude Projectのナレッジに直接APIで追加する」ことはできない。**
  claude.aiのProjectナレッジは現時点でAnthropicの公開APIから書き込む
  手段が無い。実現可能な方法は、Claude Projectの設定画面でGoogle Drive
  のフォルダをナレッジソースとして接続し、そのフォルダの内容が自動同期
  される、という間接的な経路。
- **Gmail通知はSMTP+アプリパスワード方式。** Workspace管理者権限が要る
  ドメイン全体の委任は使わず、通知元のGoogleアカウントで2段階認証を
  有効化してアプリパスワードを発行する方式にしている（個人利用前提）。
- **この開発環境にはNotion/Anthropic/Google Cloudの実アカウント・APIキーが
  無いため、実際のポーリング・API呼び出しは未テスト。** 構文・import
  チェックのみ実施済み。

## セットアップ

### 1. Notion側の準備

1. https://www.notion.so/my-integrations で「New integration」を作成し、
   発行されたトークンを `NOTION_API_KEY` に設定する。
2. 文字起こしを溜めるデータベースを作成する。タイトルプロパティ（自動で
   存在）に加えて、チェックボックス型のプロパティ（名前は何でもよいが、
   既定値は「処理済み」。変更する場合は `NOTION_PROCESSED_PROPERTY` も
   合わせる）を追加する。
3. そのデータベースの右上「...」→「Connections」から、作成した
   Integrationを接続（共有）する。
4. データベースのURLから `NOTION_DATABASE_ID` を取得する
   （`https://www.notion.so/xxxx?v=yyyy` の `xxxx` 部分）。

### 2. 必要な認証情報を揃える

| 項目 | 入手元 |
|---|---|
| `NOTION_API_KEY` / `NOTION_DATABASE_ID` | 上記「1. Notion側の準備」 |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/ |
| Google サービスアカウントJSON | Google Cloud Console → IAMと管理 → サービスアカウント。Drive APIとSheets APIを有効化し、保存先フォルダとタスクシートをそのサービスアカウントのメールアドレスに共有（編集者権限）しておく |
| `DRIVE_FOLDER_ID` | 保存先Google DriveフォルダのURLに含まれるID |
| `TASK_SHEET_ID` | タスク管理用に事前作成したGoogle SheetsのURLに含まれるID。1行目に `日付 / 会議名 / 担当者 / タスク / 期限 / 完了` のヘッダーを入れておく |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | 通知を送るGoogleアカウントで2段階認証を有効化し、アカウント設定の「アプリパスワード」で発行 |
| `NOTIFY_EMAIL_TO` | 通知を受け取りたいメールアドレス |

`.env.example` を `.env` にコピーして値を埋める。

### 3. ローカルで動作確認（構文・起動確認のみ）

```bash
pip install -r requirements.txt
python -m app.main
```

`http://localhost:8080/healthz` が `{"status": "ok"}` を返せば起動は成功。
`/poll` の一連の処理は実際のNotion/Anthropic/Googleの認証情報が無いと
テストできない。ローカルで試す場合は環境変数を設定した上で
`curl -X POST http://localhost:8080/poll` を実行する。

### 4. Cloud Runへデプロイ（例）

```bash
gcloud run deploy notta-minutes-bot \
  --source . \
  --region asia-northeast1 \
  --no-allow-unauthenticated \
  --set-env-vars NOTION_API_KEY=xxx,NOTION_DATABASE_ID=xxx,ANTHROPIC_API_KEY=xxx,DRIVE_FOLDER_ID=xxx \
  --set-secrets GOOGLE_SERVICE_ACCOUNT_JSON=/secrets/sa.json=notta-bot-sa:latest
```

サービスアカウントJSONはSecret Managerに登録してマウントする想定
（上記はその一例。環境に合わせて調整が必要）。`/poll`は外部に晒す必要が
無いエンドポイントなので `--no-allow-unauthenticated` にし、Cloud Scheduler
からのOIDC認証付き呼び出しのみ許可するのが望ましい。

### 5. Cloud Schedulerで定期実行を設定

```bash
gcloud scheduler jobs create http notta-minutes-poll \
  --schedule="*/15 * * * *" \
  --uri="https://<Cloud RunのURL>/poll" \
  --http-method=POST \
  --oidc-service-account-email=<Cloud Run起動用サービスアカウント> \
  --location=asia-northeast1
```

OIDC認証を使わない場合は、`POLL_SHARED_SECRET` を設定しURLに
`?secret=...` を付与する簡易方式でも代用できる。

### 6. Claude Project側の設定（一度だけ）

claude.aiのProject設定からGoogle Drive連携を有効化し、`DRIVE_FOLDER_ID`
のフォルダをナレッジソースとして追加する。これで新しい文字起こし・議事録
ファイルが自動的にProjectのナレッジに反映される（同期タイミングはClaude
側の仕様に依存）。

## 次に決めること

- Notta→Notionの手動エクスポートが許容できるか。許容できない場合は
  Notta公式MCP/CLIのヘッドレス認証方法をNottaサポートに確認し、
  Notion中継を外してNotta直結に切り替える。
- タスクシートの「完了」列をどう運用するか（手動チェックのみで十分か、
  将来的に通知や集計を増やすか）。
