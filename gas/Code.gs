/**
 * GAS Web App: YouTube要約 / Twitterおすすめ をスプレッドシートに書き込む
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

// シート別の設定
const SHEET_CONFIG = {
  youtube: {
    name: "YouTube要約",
    idColumn: 2, // 動画ID列
    headers: ["登録日時", "動画ID", "タイトル", "チャンネル", "URL", "再生時間(秒)", "投稿日", "字幕あり", "要約"],
    rowMapper: function (row, now) {
      return [
        now,
        row.video_id || "",
        row.title || "",
        row.channel || "",
        row.url || "",
        row.duration || 0,
        row.upload_date || "",
        row.has_subtitles ? "○" : "×",
        row.summary || "",
      ];
    },
    idExtractor: function (row) {
      return row.video_id;
    },
  },
  twitter: {
    name: "Twitterおすすめ",
    idColumn: 2, // ツイートURL列
    headers: ["登録日時", "URL", "投稿者", "ハンドル", "本文", "カテゴリ", "投稿日時"],
    rowMapper: function (row, now) {
      return [
        now,
        row.url || "",
        row.author || "",
        row.handle || "",
        row.text || "",
        row.category || "",
        row.timestamp || "",
      ];
    },
    idExtractor: function (row) {
      return row.url;
    },
  },
};

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const rows = data.rows;
    const sheetType = data.sheet || "youtube"; // デフォルトはyoutube（後方互換）

    if (!rows || rows.length === 0) {
      return jsonResponse({ status: "ok", message: "No rows to add" });
    }

    const config = SHEET_CONFIG[sheetType];
    if (!config) {
      return jsonResponse({ status: "error", message: "Unknown sheet type: " + sheetType });
    }

    const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
    let sheet = ss.getSheetByName(config.name);

    // シートがなければ作成してヘッダーを追加
    if (!sheet) {
      sheet = ss.insertSheet(config.name);
      sheet.appendRow(config.headers);
      sheet.getRange(1, 1, 1, config.headers.length).setFontWeight("bold");
      sheet.setFrozenRows(1);
    }

    // 既存IDを取得（重複防止）
    const existingIds = new Set();
    const lastRow = sheet.getLastRow();
    if (lastRow > 1) {
      const idCol = sheet.getRange(2, config.idColumn, lastRow - 1, 1).getValues();
      idCol.forEach(function (r) {
        if (r[0]) existingIds.add(r[0].toString());
      });
    }

    let addedCount = 0;
    const now = new Date();

    rows.forEach(function (row) {
      const id = config.idExtractor(row);
      if (!id || existingIds.has(id.toString())) {
        return;
      }
      sheet.appendRow(config.rowMapper(row, now));
      addedCount++;
    });

    return jsonResponse({
      status: "ok",
      sheet: config.name,
      added: addedCount,
      skipped: rows.length - addedCount,
    });
  } catch (error) {
    return jsonResponse({ status: "error", message: error.toString() });
  }
}

// テスト用: GETでアクセスして動作確認
function doGet(e) {
  return jsonResponse({
    status: "ok",
    message: "Recommend Feeder API is running",
    spreadsheet_id: SPREADSHEET_ID,
    supported_sheets: Object.keys(SHEET_CONFIG),
  });
}

function jsonResponse(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(
    ContentService.MimeType.JSON
  );
}
