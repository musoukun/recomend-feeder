/**
 * GAS Web App: YouTube要約をスプレッドシートに書き込む
 *
 * デプロイ手順:
 * 1. Google Apps Script (https://script.google.com) で新規プロジェクト作成
 * 2. このコードを貼り付け
 * 3. デプロイ → 新しいデプロイ → ウェブアプリ
 *    - 実行ユーザー: 自分
 *    - アクセス: 全員
 * 4. デプロイURLを .env の GAS_WEBAPP_URL に設定
 */

const SPREADSHEET_ID = "1kY4vVo0RVT_4Gbv3GcHOMLYPedr5z_rAnDIgOeCfBrs";
const SHEET_NAME = "YouTube要約";

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const rows = data.rows;

    if (!rows || rows.length === 0) {
      return ContentService.createTextOutput(
        JSON.stringify({ status: "ok", message: "No rows to add" })
      ).setMimeType(ContentService.MimeType.JSON);
    }

    const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
    let sheet = ss.getSheetByName(SHEET_NAME);

    // シートがなければ作成してヘッダーを追加
    if (!sheet) {
      sheet = ss.insertSheet(SHEET_NAME);
      sheet.appendRow([
        "登録日時",
        "動画ID",
        "タイトル",
        "チャンネル",
        "URL",
        "再生時間(秒)",
        "投稿日",
        "字幕あり",
        "要約",
      ]);
      // ヘッダー行を太字に
      sheet.getRange(1, 1, 1, 9).setFontWeight("bold");
      sheet.setFrozenRows(1);
    }

    // 既存の動画IDを取得（重複防止）
    const existingIds = new Set();
    const lastRow = sheet.getLastRow();
    if (lastRow > 1) {
      const idColumn = sheet.getRange(2, 2, lastRow - 1, 1).getValues();
      idColumn.forEach(function (row) {
        if (row[0]) existingIds.add(row[0].toString());
      });
    }

    let addedCount = 0;
    const now = new Date();

    rows.forEach(function (row) {
      // 重複スキップ
      if (existingIds.has(row.video_id)) {
        return;
      }

      sheet.appendRow([
        now,
        row.video_id || "",
        row.title || "",
        row.channel || "",
        row.url || "",
        row.duration || 0,
        row.upload_date || "",
        row.has_subtitles ? "○" : "×",
        row.summary || "",
      ]);
      addedCount++;
    });

    return ContentService.createTextOutput(
      JSON.stringify({
        status: "ok",
        added: addedCount,
        skipped: rows.length - addedCount,
      })
    ).setMimeType(ContentService.MimeType.JSON);
  } catch (error) {
    return ContentService.createTextOutput(
      JSON.stringify({ status: "error", message: error.toString() })
    ).setMimeType(ContentService.MimeType.JSON);
  }
}

// テスト用: GETでアクセスして動作確認
function doGet(e) {
  return ContentService.createTextOutput(
    JSON.stringify({
      status: "ok",
      message: "YouTube Summary API is running",
      spreadsheet_id: SPREADSHEET_ID,
    })
  ).setMimeType(ContentService.MimeType.JSON);
}
