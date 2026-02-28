const express = require("express");
const path = require("path");
const RSSParser = require("rss-parser");

const app = express();
const parser = new RSSParser({
  timeout: 10000,
  headers: {
    "User-Agent": "IranNewsTimeline/1.0",
  },
});

const PORT = process.env.PORT || 3000;

// RSS feeds from major news wires and outlets
const RSS_FEEDS = [
  {
    name: "Reuters World",
    url: "https://feeds.reuters.com/Reuters/worldNews",
  },
  {
    name: "AP News",
    url: "https://rsshub.app/apnews/topics/world-news",
  },
  {
    name: "Al Jazeera",
    url: "https://www.aljazeera.com/xml/rss/all.xml",
  },
  {
    name: "BBC World",
    url: "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
  },
  {
    name: "NPR World",
    url: "https://feeds.npr.org/1004/rss.xml",
  },
  {
    name: "The Guardian World",
    url: "https://www.theguardian.com/world/middleeast/rss",
  },
  {
    name: "CNN World",
    url: "http://rss.cnn.com/rss/edition_world.rss",
  },
  {
    name: "France24 Middle East",
    url: "https://www.france24.com/en/middle-east/rss",
  },
];

// Keywords to filter Iran-related news
const IRAN_KEYWORDS = [
  "iran",
  "iranian",
  "tehran",
  "isfahan",
  "khamenei",
  "persian gulf",
  "strait of hormuz",
  "irgc",
  "revolutionary guard",
  "hezbollah",
  "proxy",
  "sanctions",
  "enrichment",
  "nuclear",
  "centrifuge",
  "natanz",
  "fordow",
  "parchin",
  "araghchi",
  "pezeshkian",
  "quds force",
  "basij",
  "ayatollah",
];

function matchesIranKeywords(text) {
  if (!text) return false;
  const lower = text.toLowerCase();
  return IRAN_KEYWORDS.some((kw) => lower.includes(kw));
}

function categorizeEvent(title, content) {
  const text = ((title || "") + " " + (content || "")).toLowerCase();
  if (/military|strike|bomb|attack|missile|drone|airstr/i.test(text))
    return "military";
  if (/diplomat|negotiat|talk|summit|un |united nations|treaty/i.test(text))
    return "diplomacy";
  if (/sanction|economy|oil|trade|embargo|currency|rial/i.test(text))
    return "sanctions";
  if (/nuclear|enrichment|centrifuge|iaea|uranium|atomic/i.test(text))
    return "nuclear";
  if (/humanitarian|refugee|civilian|casualt|aid|crisis/i.test(text))
    return "humanitarian";
  if (/protest|unrest|dissent|opposition|rally/i.test(text)) return "domestic";
  return "general";
}

// In-memory cache
let cachedArticles = [];
let lastFetchTime = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

async function fetchAllFeeds() {
  const now = Date.now();
  if (now - lastFetchTime < CACHE_TTL && cachedArticles.length > 0) {
    return cachedArticles;
  }

  const allArticles = [];
  const feedPromises = RSS_FEEDS.map(async (feed) => {
    try {
      const parsed = await parser.parseURL(feed.url);
      const items = (parsed.items || [])
        .filter((item) => {
          const text =
            (item.title || "") +
            " " +
            (item.contentSnippet || "") +
            " " +
            (item.content || "");
          return matchesIranKeywords(text);
        })
        .map((item) => ({
          title: item.title || "Untitled",
          summary: truncate(
            item.contentSnippet || item.content || "No summary available.",
            300
          ),
          link: item.link || "#",
          source: feed.name,
          date: item.isoDate || item.pubDate || new Date().toISOString(),
          category: categorizeEvent(item.title, item.contentSnippet),
        }));
      return items;
    } catch (err) {
      console.error(`Failed to fetch ${feed.name}: ${err.message}`);
      return [];
    }
  });

  const results = await Promise.allSettled(feedPromises);
  for (const result of results) {
    if (result.status === "fulfilled") {
      allArticles.push(...result.value);
    }
  }

  // Sort by date descending
  allArticles.sort((a, b) => new Date(b.date) - new Date(a.date));

  // Deduplicate by similar titles
  const seen = new Set();
  const deduped = allArticles.filter((article) => {
    const key = normalizeTitle(article.title);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  cachedArticles = deduped;
  lastFetchTime = now;
  return deduped;
}

function normalizeTitle(title) {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 60);
}

function truncate(text, maxLen) {
  if (!text) return "";
  // Strip HTML tags
  const clean = text.replace(/<[^>]*>/g, "").trim();
  if (clean.length <= maxLen) return clean;
  return clean.slice(0, maxLen).replace(/\s\S*$/, "") + "...";
}

// API endpoint
app.get("/api/news", async (req, res) => {
  try {
    const articles = await fetchAllFeeds();

    // Group by date for timeline
    const grouped = {};
    for (const article of articles) {
      const dateKey = new Date(article.date).toISOString().split("T")[0];
      if (!grouped[dateKey]) grouped[dateKey] = [];
      grouped[dateKey].push(article);
    }

    res.json({
      lastUpdated: new Date().toISOString(),
      totalArticles: articles.length,
      feedsScanned: RSS_FEEDS.length,
      timeline: grouped,
      articles: articles,
    });
  } catch (err) {
    console.error("Error fetching news:", err);
    res.status(500).json({ error: "Failed to fetch news updates" });
  }
});

// Serve static files
app.use(express.static(path.join(__dirname, "public")));

// Fallback to index.html
app.get("*", (req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

app.listen(PORT, () => {
  console.log(`Iran News Timeline running at http://localhost:${PORT}`);
  console.log(`Scanning ${RSS_FEEDS.length} news feeds for Iran-related updates`);
});
