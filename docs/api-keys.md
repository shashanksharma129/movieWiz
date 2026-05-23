# API Keys

movieWiz requires two API keys. Both can be set in `.env` or entered directly in the Streamlit sidebar.

---

## Anthropic API Key

Used for: LLM extraction via Claude Sonnet 4.6

### Steps

1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Sign up or log in
3. Navigate to **API Keys** in the left sidebar
4. Click **Create Key**, give it a name (e.g. "movieWiz")
5. Copy the key — it starts with `sk-ant-...`
6. Add to `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

### Cost

Claude Sonnet 4.6 is priced at **$3.00 / 1M input tokens** and **$15.00 / 1M output tokens**.

A typical movieWiz run on a <50 KB chat costs approximately **$0.05–$0.15** total. The local MD5 cache means you pay this cost only once per unique chat file.

Prompt caching is enabled by default in movieWiz — the large system prompt is cached across all chunks in a single run, reducing input token costs by ~90% for the cached portion.

---

## TMDB API Key

Used for: Movie posters, genres, release year, TMDB score

TMDB (The Movie Database) is free for non-commercial use.

### Steps

1. Go to [themoviedb.org](https://www.themoviedb.org/) and create a free account
2. Navigate to **Settings → API** (direct link: [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api))
3. Click **Request an API Key**
4. Select **Developer** (personal/hobby use)
5. Fill in the application details (app name, description, URL — anything works for personal use)
6. Copy the **API Key (v3 auth)** — it's a 32-character hex string
7. Add to `.env`:
   ```
   TMDB_API_KEY=your32hexkeyhere
   ```

### Rate limits

TMDB's free tier allows up to **40 requests per 10 seconds**. movieWiz makes 2 sequential requests per movie (search + details). For a chat with 20 unique movies, that's 40 requests well within the limit.

---

## Using Keys Without a `.env` File

If you prefer not to create a `.env` file, you can enter both keys directly in the Streamlit sidebar each time you run the app. The keys are stored in memory only for that session — they are never written to disk by the app.

---

## Security Notes

- Never commit your `.env` file — it is listed in `.gitignore`
- The `.env.example` file contains only placeholder values and is safe to commit
- TMDB keys are passed as a query parameter (`?api_key=...`) in API calls, which means they appear in HTTP server logs on TMDB's side — this is acceptable for personal use but be aware if sharing the tool
- Anthropic keys are sent via the `x-api-key` header, which does not appear in URLs
