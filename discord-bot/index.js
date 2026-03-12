const { Client, GatewayIntentBits, EmbedBuilder } = require("discord.js");
const RSSParser = require("rss-parser");
const fs = require("fs");
const path = require("path");
const dotenv = require("dotenv");

dotenv.config();

const DISCORD_TOKEN = process.env.DISCORD_TOKEN;
const POLL_INTERVAL = (parseInt(process.env.POLL_INTERVAL_MINUTES, 10) || 10) * 60 * 1000;
const POSTED_FILE = path.join(__dirname, "posted.json");
const CHANNELS_FILE = path.join(__dirname, "channels.json");

// --- チャンネル設定読み込み ---

function loadChannelConfig() {
  if (!fs.existsSync(CHANNELS_FILE)) {
    console.error("channels.json not found. Copy channels.json.example to channels.json and configure.");
    process.exit(1);
  }
  const config = JSON.parse(fs.readFileSync(CHANNELS_FILE, "utf-8"));
  if (!Array.isArray(config) || config.length === 0) {
    console.error("channels.json is empty or invalid.");
    process.exit(1);
  }
  return config;
}

const CHANNEL_CONFIG = loadChannelConfig();

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
  const arr = [...posted];
  const trimmed = arr.slice(-2000);
  fs.writeFileSync(POSTED_FILE, JSON.stringify(trimmed), "utf-8");
}

// --- カテゴリ別の色とラベル ---

const CATEGORY_CONFIG = {
  "ai-tech": { color: 0x00bcd4, label: "AI・テック" },
  "ai-career": { color: 0x2196f3, label: "AI時代の働き方・雇用" },
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
  // content:encodedからHTMLタグを除去してツイート本文を取得
  const rawContent = (item.content || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  const text = rawContent || item.contentSnippet || "";
  const description =
    text.length > 300 ? text.substring(0, 300) + "..." : text;

  const embed = new EmbedBuilder()
    .setColor(config.color)
    .setTitle(item.title || "Tweet")
    .setURL(item.link || "")
    .setDescription(description)
    .setFooter({ text: config.label })
    .setTimestamp(item.isoDate ? new Date(item.isoDate) : new Date());

  const imgMatch = (item.content || "").match(/src="(https:\/\/pbs\.twimg\.com\/[^"]+)"/);
  if (imgMatch) {
    embed.setThumbnail(imgMatch[1]);
  }

  return embed;
}

// --- メインループ ---

async function pollFeeds(client, posted) {
  const parser = new RSSParser();
  let newCount = 0;

  // フィードURLごとにパース結果をキャッシュ（同じフィードを複数チャンネルで使う場合の効率化）
  const feedCache = new Map();

  for (const entry of CHANNEL_CONFIG) {
    const { name, channel_id, feeds } = entry;
    if (!feeds || feeds.length === 0) continue;

    // チャンネル取得
    let channel = client.channels.cache.get(channel_id);
    if (!channel) {
      try {
        channel = await client.channels.fetch(channel_id);
      } catch (err) {
        console.error(`Channel "${name}" (${channel_id}) not found:`, err.message);
        continue;
      }
    }

    for (const feedUrl of feeds) {
      const category = detectCategory(feedUrl);

      // フィードをキャッシュから取得、なければfetch
      if (!feedCache.has(feedUrl)) {
        try {
          const feed = await parser.parseURL(feedUrl);
          feedCache.set(feedUrl, feed.items || []);
        } catch (err) {
          console.error(`Failed to fetch feed ${feedUrl}:`, err.message);
          feedCache.set(feedUrl, []);
          continue;
        }
      }

      const items = [...feedCache.get(feedUrl)].reverse();

      for (const item of items) {
        // チャンネル+GUIDで重複管理（同じ記事でもチャンネルが違えば投稿）
        const guid = item.guid || item.link || item.title;
        const postedKey = `${channel_id}:${guid}`;
        if (!guid || posted.has(postedKey)) continue;

        const embed = buildEmbed(item, category);
        // 要約があればコメントとして添える（RSSのdescriptionに格納）
        const summary = item.contentSnippet || "";
        const content = summary && summary.length <= 100 ? `💬 ${summary}` : "";
        try {
          await channel.send({ content: content || undefined, embeds: [embed] });
          posted.add(postedKey);
          newCount++;
          await sleep(1000);
        } catch (err) {
          console.error(`Failed to post to "${name}":`, err.message);
        }
      }
    }
  }

  if (newCount > 0) {
    savePosted(posted);
    console.log(`Posted ${newCount} new items.`);
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
  console.log(`Poll interval: ${POLL_INTERVAL / 1000 / 60} minutes`);
  console.log("Channel config:");
  for (const entry of CHANNEL_CONFIG) {
    console.log(`  ${entry.name} (${entry.channel_id}): ${entry.feeds.length} feed(s)`);
  }

  const posted = loadPosted();

  // 初回チェック
  await pollFeeds(client, posted);

  // 定期チェック
  setInterval(() => pollFeeds(client, posted), POLL_INTERVAL);
});

client.login(DISCORD_TOKEN);
