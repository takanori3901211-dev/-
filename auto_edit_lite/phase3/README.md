# Phase3 — クラウド完全自動化（設計・準備段階）

Google Driveの「受付」フォルダに素材を置くだけで、Cloud Run上の
`auto_edit_lite`が自動で編集し、「完成」フォルダに書き戻す仕組み。

## 重要: 現在の状態

**このディレクトリのコードはまだGCP上でのデプロイ・実機検証を行っていない。**
開発環境にGCPの認証情報が無く（`gcloud auth list`で未認証）、Dockerデーモンも
サンドボックスの権限制限で起動できなかったため、以下の範囲でのみ検証済み:

- `cloudrun_server.py`: Flaskサーバーとして**ローカルで起動し**、`/health`が
  正常応答すること、`/process`が必須パラメータ不足時に400エラーを返す
  ことを確認済み（Drive APIを実際に呼び出す部分は未検証）。
- `Code.gs` / `Dockerfile`: 構文・設計レベルの作成のみ。実際にApps Script
  エディタや`gcloud run deploy`で動かした検証はまだ行っていない。

デプロイ前に、**小さなテストフォルダ・テスト素材で一度通しの動作確認を
行うこと**を強く推奨する。

## アーキテクチャ

```
Google Drive
 ├─ 受付/
 │   └─ 案件名/
 │       ├─ 商品情報.txt
 │       └─ clip1.mp4, clip2.mp4, ...
 ├─ 処理中/   (処理開始時にApps Scriptが移動させる)
 ├─ 完成/
 │   └─ 案件名/
 │       ├─ final.mp4
 │       └─ plan.json (または seg_ai.json)
 └─ エラー/   (Cloud Run側が失敗した場合、error.txt付きで移動される)

Google Apps Script (5分おきのトリガー)
 └─ processOneJob(): 受付フォルダを1件だけ処理中に移動し、
    Cloud RunサービスにHTTP POSTで処理を依頼する

Cloud Run (cloudrun_server.py)
 └─ /process: 指定フォルダの素材をダウンロード→make_video.py実行
    →結果を指定フォルダにアップロード
```

## デプロイ手順（想定・未検証）

### 1. GCPプロジェクトの準備

```bash
gcloud auth login
gcloud projects create <プロジェクトID>   # または既存プロジェクトを使う
gcloud config set project <プロジェクトID>
gcloud billing projects link <プロジェクトID> --billing-account=<課金アカウントID>
gcloud services enable run.googleapis.com drive.googleapis.com
```

### 2. サービスアカウントの作成とDrive共有

```bash
gcloud iam service-accounts create auto-edit-lite-runner
```

作成されたサービスアカウントのメールアドレス（`auto-edit-lite-runner@<プロジェクトID>.iam.gserviceaccount.com`）
を、Drive上の「受付」「処理中」「完成」「エラー」フォルダすべてに
**編集者として共有**する（Driveの共有設定から手動で行う）。

### 3. Gemini APIキーをSecret Managerに登録（推奨）

```bash
echo -n "取得したGemini APIキー" | gcloud secrets create gemini-api-key --data-file=-
```

### 4. Cloud Runへデプロイ

```bash
cd auto_edit_lite
gcloud run deploy auto-edit-lite \
  --source . \
  --dockerfile phase3/Dockerfile \
  --service-account auto-edit-lite-runner@<プロジェクトID>.iam.gserviceaccount.com \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest \
  --set-env-vars SHARED_SECRET=<ランダムな文字列> \
  --region asia-northeast1 \
  --no-allow-unauthenticated \
  --memory 2Gi --cpu 2 --timeout 300
```

**重要: `--timeout`はGoogle Apps Scriptの実行時間上限(個人アカウントは6分、
Google Workspaceアカウントは30分)より必ず短くすること。** `Code.gs`の
`processOneJob()`はCloud Runの`/process`呼び出し(`UrlFetchApp.fetch`)を
同期的に待つ設計になっており、Cloud Run側が応答する前にApps Script自体が
6分で強制終了すると、その例外は`try/catch`で捕まえられずジョブが
「処理中」フォルダに入ったまま動かなくなる(次のトリガーは「受付」フォルダ
しか見ないため、スタックしたジョブは再試行されない)。`--timeout 300`
(5分)としてCloud Run側がApps Scriptより先にタイムアウトし、必ずHTTPの
エラー応答を返すようにすることで、この「サイレントに止まる」事態を防ぐ。
本番でクリップ本数が増え処理が5分を超える場合は、このタイムアウト値を
単純に伸ばすのではなく、同期呼び出しをやめて非同期(ジョブ投げて別トリガーで
完了確認)に設計変更する必要がある。

`--no-allow-unauthenticated`にする場合、Apps Script側もOAuth認証付きで
呼び出す必要がある（`UrlFetchApp`に`ScriptApp.getOAuthToken()`のBearer
トークンを付与する等、`Code.gs`の追加対応が必要。現状の`Code.gs`は
`SHARED_SECRET`ヘッダーのみでの簡易認証を前提にしており、
`--allow-unauthenticated`運用を想定している。本番では
Cloud Runの認証機構を使うよう強化することを推奨）。

デプロイ完了後に表示されるURLを、Apps Scriptのスクリプトプロパティ
`CLOUD_RUN_URL`に設定する。

### 5. Google Apps Scriptのセットアップ

1. Google Driveで新規のApps Scriptプロジェクトを作成（または
   https://script.google.com/ から新規作成）
2. `apps_script/Code.gs`の内容を貼り付け
3. プロジェクトの設定 → マニフェストファイルを表示 → `apps_script/appsscript.json`
   の内容を反映
4. 「プロジェクトの設定」→「スクリプト プロパティ」で以下を設定:
   - `INBOX_FOLDER_ID` / `PROCESSING_FOLDER_ID` / `DONE_FOLDER_ID` / `ERROR_FOLDER_ID`
     （各Driveフォルダを作成し、そのIDを設定）
   - `CLOUD_RUN_URL`（手順4で取得したURL）
   - `SHARED_SECRET`（手順4で設定したものと同じ値）
5. エディタから`setupTrigger`関数を1度だけ実行し、5分おきのトリガーを登録する

## コスト

`仕様書.md`のコスト見積もり（月間投稿本数別の目安）を参照。Cloud Runは
リクエスト処理時間に応じた従量課金のため、本番相当テスト（15クリップ/約2分）
を基準にすると、1本あたりの処理コストは小さい見込みだが、実際の課金額は
GCPコンソールで確認すること。

## 残っている未決定事項

- 月間想定投稿本数の確定（コスト精度のため）
- GCPアカウント・課金設定の作成タイミング
- Cloud Runの認証方式（`SHARED_SECRET`簡易認証のままでよいか、
  OAuth等より堅牢な方式にするか）
- 実際のデプロイ・通しテストの実施
- 本番で1件の処理が5分を超える規模になった場合の、同期呼び出し
  (`UrlFetchApp.fetch`で待つ現在の設計)から非同期設計への切り替え

## デプロイ前レビューで見つけた問題（コード側で修正済み）

実際のGCPデプロイはまだできていないが、クラウド開発環境にffmpeg/
fontconfigが入っていたため、`Dockerfile`が入れるフォント構成をこの
環境で再現して検証できた。見つかった問題は`lite_edit.py`側を修正済み:

- **字幕フォントが実際には存在しなかった**: `ASS_HEADER`が指定していた
  `Noto Sans CJK JP Black`は、`Dockerfile`がインストールする
  `fonts-noto-cjk`パッケージには含まれていない(同パッケージはRegular/Boldのみ
  収録。Black等の追加ウェイトは別パッケージ`fonts-noto-cjk-extra`
  (展開後214MB)で、`Dockerfile`はこれを入れていない)。実際にこの環境で
  `fonts-noto-cjk`だけを入れてffmpegの`ass`フィルタに通したところ、
  指定フォントが見つからずfontconfigが無関係な他フォントにフォール
  バックすることを確認した。`ASS_HEADER`のフォント指定を実際に存在する
  `Noto Sans CJK JP`(Boldフラグで太字化)に変更し、`fonts-noto-cjk`のみで
  正しく`NotoSansCJK-Bold.ttc`に解決されることを確認済み。
  `fonts-noto-cjk-extra`を追加してBlackウェイトそのものを使う案も
  あったが、JP以外の言語分も含めて144MBのダウンロードが増えるため
  見送った(デプロイ後に見た目を確認し、太さが足りなければ検討)。
