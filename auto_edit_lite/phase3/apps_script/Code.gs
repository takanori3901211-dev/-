/**
 * TikTok Shop自動編集 Phase3 — Driveフォルダ監視・Cloud Run呼び出し。
 *
 * フォルダ構成（あらかじめ手動で作成し、IDをスクリプトプロパティに設定する）:
 *   受付/    ここに「案件名」フォルダを作り、商品情報.txt + 動画ファイルを置く
 *   処理中/  処理開始時に受付から移動される（二重処理防止）
 *   完成/    final.mp4等の出力先。案件名と同じ名前のフォルダが作られる
 *   エラー/  Cloud Run側が失敗した場合、エラー内容と共に移動される
 *
 * 未検証: GCPアクセスが無い開発環境で作成したコードで、実際にApps Script
 * エディタに貼り付けて動かした検証はまだ行っていない。デプロイ時に
 * 小さなテストフォルダで一度动作確認すること。
 *
 * スクリプトプロパティ（「プロジェクトの設定」→「スクリプト プロパティ」で設定）:
 *   INBOX_FOLDER_ID    受付フォルダのID
 *   PROCESSING_FOLDER_ID 処理中フォルダのID
 *   DONE_FOLDER_ID     完成フォルダのID
 *   ERROR_FOLDER_ID    エラーフォルダのID
 *   CLOUD_RUN_URL      Cloud RunサービスのURL(例: https://xxx-xxx.a.run.app)
 *   SHARED_SECRET      cloudrun_server.pyのSHARED_SECRET環境変数と同じ値
 */

function processOneJob() {
  const props = PropertiesService.getScriptProperties();
  const inboxId = props.getProperty('INBOX_FOLDER_ID');
  const processingId = props.getProperty('PROCESSING_FOLDER_ID');
  const doneId = props.getProperty('DONE_FOLDER_ID');
  const errorId = props.getProperty('ERROR_FOLDER_ID');
  const cloudRunUrl = props.getProperty('CLOUD_RUN_URL');
  const sharedSecret = props.getProperty('SHARED_SECRET');

  if (!inboxId || !processingId || !doneId || !errorId || !cloudRunUrl) {
    Logger.log('スクリプトプロパティが不足しています。設定を確認してください。');
    return;
  }

  const inbox = DriveApp.getFolderById(inboxId);
  const jobFolders = inbox.getFolders();

  if (!jobFolders.hasNext()) {
    Logger.log('受付フォルダに未処理の案件はありません。');
    return;
  }

  // 1回のトリガー実行では1件だけ処理する(Apps Scriptの実行時間6分制限のため)。
  const jobFolder = jobFolders.next();
  const jobName = jobFolder.getName();

  const processingParent = DriveApp.getFolderById(processingId);
  moveFolder_(jobFolder, inbox, processingParent);

  const doneParent = DriveApp.getFolderById(doneId);
  const outputFolder = doneParent.createFolder(jobName);

  Logger.log('処理開始: ' + jobName);

  try {
    const payload = {
      input_folder_id: jobFolder.getId(),
      output_folder_id: outputFolder.getId(),
    };
    const options = {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true,
    };
    if (sharedSecret) {
      options.headers = { 'X-Shared-Secret': sharedSecret };
    }

    const response = UrlFetchApp.fetch(cloudRunUrl + '/process', options);
    const code = response.getResponseCode();
    const body = response.getContentText();

    if (code === 200) {
      Logger.log('完了: ' + jobName + ' -> ' + body);
    } else {
      Logger.log('失敗: ' + jobName + ' (HTTP ' + code + ') ' + body);
      handleFailure_(jobFolder, processingParent, errorId, body);
    }
  } catch (e) {
    Logger.log('例外: ' + jobName + ' ' + e);
    handleFailure_(jobFolder, processingParent, errorId, String(e));
  }
}

function handleFailure_(jobFolder, processingParent, errorId, message) {
  const errorParent = DriveApp.getFolderById(errorId);
  const note = Utilities.newBlob(message, 'text/plain', 'error.txt');
  jobFolder.createFile(note);
  moveFolder_(jobFolder, processingParent, errorParent);
}

function moveFolder_(folder, fromParent, toParent) {
  toParent.addFolder(folder);
  fromParent.removeFolder(folder);
}

/**
 * 初回セットアップ時に1度だけ実行する: 5分おきのトリガーを登録する。
 * (Apps Scriptエディタで関数一覧からこれを選んで実行するか、
 *  デプロイ用のセットアップ時にのみ呼び出すこと。二重登録に注意)
 */
function setupTrigger() {
  ScriptApp.newTrigger('processOneJob')
    .timeBased()
    .everyMinutes(5)
    .create();
}
