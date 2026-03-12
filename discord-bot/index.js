const { Client, GatewayIntentBits, EmbedBuilder } = require("discord.js");
const RSSParser = require("rss-parser");
const fs = require("fs");
const path = require("path");
const dotenv = require("dotenv");

dotenv.config();

const DISCORD_TOKEN = process.env.DISCORD_TOKEN;
const FEED_URLS = (process.env.FEED_URLS || "").split(",").filter(Boolean);
const POLL_INTERVAL = (parseInt(process.env.POLL_INTERVAL_MINUTES, 10) || 10) * 60 * 1000;
const POSTED_FILE = path.join(__dirname, "posted.json");

// チャンネル設定をパース
// 形式: DISCORD_CHANNELS=サーバー1名:チャンネルID1,サーバー2名:チャンネルID2
// 旧形式 DISCORD_CHANNEL_ID も後方互換でサポート
function parseChannels() {
  const channels = [];
  const channelsEnv = process.env.DISCORD_CHANNELS || "";

  if (channelsEnv) {
    for (const entry of channelsEnv.split(",").filter(Boolean)) {
      const sep = entry.lastIndexOf(":");
      if (sep > 0) {
        channels.push({
          name: entry.substring(0, sep).trim(),
          id: entry.substring(sep + 1).trim(),
        });
      } else {
        channels.push({ name: "default", id: entry.trim() });
      }
    }
  }

  // 後方互換: DISCORD_CHANNEL_ID
  if (channels.length === 0 && process.env.DISCORD_CHANNEL_ID) {
    channels.push({ name: "default", id: process.env.DISCORD_CHANNEL_ID });
  }

  return channels;
}

const TARGET_CHANNELS = parseChannels();

// --- 投稿済みGUID管理 ---

function loadPosted() {
  try {
    if (fs.existsSync(POSTED_FILE)) {
      return new Set(JSON.parse(fs.readFileSync(POSTED_FILE, "utf-8")));
    }
  } catch {
    // ignore
  }
  return new Set();
}

function savePosted(posted) {
  // 直近2000件だけ保持（メモリ節約）
  const arr = [...posted];
  const trimmed = arr.slice(-2000);
  fs.writeFileSync(POSTED_FILE, JSON.stringify(trimmed), "utf-8");
}

// --- カテゴリ別の色とラベル ---

const CATEGORY_CONFIG = {
  ai: { color: 0x00bcd4, label: "AI・テック" },
  politics: { color: 0xe53935, label: "政治" },
  romance: { color: 0xe91e63, label: "恋愛" },
  adult: { color: 0x9c27b0, label: "アダルト" },
  news: { color: 0xff9800, label: "ニュース" },
  other: { color: 0x9e9e9e, label: "その他" },
};

function detectCategory(feedUrl) {
  for (const key of Object.keys(CATEGORY_CONFIG)) {
    if (feedUrl.includes(`feed-${key}`)) return key;
  }
  return "other";
}

// --- RSS → Embed変換 ---

function buildEmbed(item, category) {
  const config = CATEGORY_CONFIG[category] || CATEGORY_CONFIG.other;
  const text = item.contentSnippet || item.content || "";
  const description =
    text.length > 300 ? text.substring(0, 300) + "..." : text;

  const embed = new EmbedBuilder()
    .setColor(config.color)
    .setTitle(item.title || "Tweet")
    .setURL(item.link || "")
    .setDescription(description)
    .setFooter({ text: config.label })
    .setTimestamp(item.isoDate ? new Date(item.isoDate) : new Date());

  // 画像があればサムネイル表示
  const imgMatch = (item.content || "").match(/src="(https:\/\/pbs\.twimg\.com\/[^"]+)"/);
  if (imgMatch) {
    embed.setThumbnail(imgMatch[1]);
  }

  return embed;
}

// --- メインループ ---

async function pollFeeds(client, posted) {
  // 全チャンネルを取得（キャッシュになければfetch）
  const channels = [];
  for (const target of TARGET_CHANNELS) {
    let ch = client.channels.cache.get(target.id);
    if (!ch) {
      try {
        ch = await client.channels.fetch(target.id);
      } catch (err) {
        console.error(`Channel "${target.name}" (${target.id}) not found:`, err.message);
        continue;
      }
    }
    channels.push({ ...target, channel: ch });
  }

  if (channels.length === 0) {
    console.error("No valid channels found. Check DISCORD_CHANNELS.");
    return;
  }

  const parser = new RSSParser();
  let newCount = 0;

  for (const feedUrl of FEED_URLS) {
    const category = detectCategory(feedUrl);
    try {
      const feed = await parser.parseURL(feedUrl);
      // 古い順に投稿（配列を反転）
      const items = [...(feed.items || [])].reverse();

      for (const item of items) {
        const guid = item.guid || item.link || item.title;
        if (!guid || posted.has(guid)) continue;

        const embed = buildEmbed(item, category);

        // 全チャンネルに投稿
        for (const { name, channel } of channels) {
          try {
            await channel.send({ embeds: [embed] });
          } catch (err) {
            console.error(`Failed to post to "${name}":`, err.message);
          }
        }

        posted.add(guid);
        newCount++;

        // レート制限対策
        await sleep(1000);
      }
    } catch (err) {
      console.error(`Failed to fetch feed ${feedUrl}:`, err.message);
    }
  }

  if (newCount > 0) {
    savePosted(posted);
    console.log(`Posted ${newCount} new items to ${channels.length} channel(s).`);
  } else {
    console.log("No new items.");
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// --- Bot起動 ---

const client = new Client({
  intents: [GatewayIntentBits.Guilds],
});

client.once("ready", async (readyClient) => {
  console.log(`Ready! Logged in as ${readyClient.user.tag}`);
  console.log(`Watching ${FEED_URLS.length} feeds`);
  console.log(`Posting to: ${TARGET_CHANNELS.map((c) => `${c.name} (${c.id})`).join(", ")}`);
  console.log(`Poll interval: ${POLL_INTERVAL / 1000 / 60} minutes`);

  const posted = loadPosted();

  // 初回チェック
  await pollFeeds(client, posted);

  // 定期チェック
  setInterval(() => pollFeeds(client, posted), POLL_INTERVAL);
});

client.login(DISCORD_TOKEN);
