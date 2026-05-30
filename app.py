import os
import shutil
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

import base64

import aggregator
import cache
import enricher
import extractor
import image_analyzer
import parser
import sessions
import summarizer
import zip_extractor

load_dotenv()

_SENTIMENT_BADGE = {
    "positive": "🟢 Positive",
    "mixed": "🟡 Mixed",
    "negative": "🔴 Negative",
}

st.set_page_config(
    page_title="movieWiz",
    page_icon="🎬",
    layout="wide",
)

# ── Auth gate ─────────────────────────────────────────────────────────────────

_app_password = st.secrets.get("app_password", "")

if not st.session_state.get("authenticated"):
    st.title("movieWiz 🎬")
    pwd = st.text_input("Password", type="password")
    if st.button("Sign in", type="primary"):
        if _app_password and pwd == _app_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()

user_id = "shared"

# ── Secrets / API keys ────────────────────────────────────────────────────────
# Keys in Streamlit secrets take precedence; sidebar inputs are shown as fallback
# so local dev still works without a secrets.toml.

_secrets_anthropic = st.secrets.get("ANTHROPIC_API_KEY", "")
_secrets_tmdb = st.secrets.get("TMDB_API_KEY", "")

# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("movieWiz")
    if st.button("Sign out", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    st.divider()

    saved = sessions.list_sessions(user_id)
    load_btn = False
    del_btn = False
    chosen_idx = 0
    if saved:
        st.subheader("Saved Sessions")
        session_labels = [f"{s['name']}  ({s['movie_count']} movies)" for s in saved]
        chosen_label = st.selectbox("Select a session", session_labels, label_visibility="collapsed")
        chosen_idx = session_labels.index(chosen_label)
        col_load, col_del = st.columns(2)
        load_btn = col_load.button("Load", use_container_width=True)
        del_btn = col_del.button("Delete", use_container_width=True)
        st.divider()

    st.subheader("New Analysis")
    uploaded_file = st.file_uploader(
        "Upload WhatsApp export (.txt or .zip with media)", type=["txt", "zip"]
    )

    if _secrets_anthropic:
        anthropic_key = _secrets_anthropic
    else:
        anthropic_key = st.text_input(
            "Anthropic API Key",
            value=os.getenv("ANTHROPIC_API_KEY", ""),
            type="password",
            help="Required for LLM extraction",
        )

    if _secrets_tmdb:
        tmdb_key = _secrets_tmdb
    else:
        tmdb_key = st.text_input(
            "TMDB API Key",
            value=os.getenv("TMDB_API_KEY", ""),
            type="password",
            help="Required for movie posters and metadata",
        )

    session_name_input = st.text_input(
        "Session name (optional)",
        placeholder="e.g. Friends group chat",
    )
    analyze_btn = st.button("Analyze Chat", type="primary", disabled=uploaded_file is None)

    if st.button("Clear all caches", type="secondary"):
        if cache.CACHE_DIR.exists():
            shutil.rmtree(cache.CACHE_DIR)
        st.session_state.clear()
        st.rerun()

    if "cache_status" in st.session_state:
        st.caption(st.session_state["cache_status"])

# ── Session load / delete ────────────────────────────────────────────────────

if saved and load_btn:
    chosen_name = saved[chosen_idx]["name"]
    loaded = sessions.load_by_name(chosen_name, user_id)
    if loaded is None:
        st.sidebar.error("Session data not found on disk.")
    else:
        st.session_state["data"] = loaded
        st.session_state["alias_map"] = loaded.get("alias_map", {})
        st.session_state["cache_status"] = f"Loaded session: {chosen_name}"
        st.rerun()

if saved and del_btn:
    sessions.delete(saved[chosen_idx]["name"], user_id)
    st.rerun()

# ── Run pipeline ─────────────────────────────────────────────────────────────

if analyze_btn:
    if anthropic_key:
        os.environ["ANTHROPIC_API_KEY"] = anthropic_key
    if tmdb_key:
        os.environ["TMDB_API_KEY"] = tmdb_key

    file_bytes = uploaded_file.read()
    is_zip = uploaded_file.name.lower().endswith(".zip")

    # ── ZIP extraction ────────────────────────────────────────────────────────
    image_map: dict[str, bytes] = {}
    if is_zip:
        _MAX_ZIP_BYTES = 50 * 1024 * 1024
        if len(file_bytes) > _MAX_ZIP_BYTES:
            st.error(
                f"ZIP file is {len(file_bytes) / 1024 / 1024:.1f} MB — limit is 50 MB. "
                "Export a smaller date range from WhatsApp."
            )
            st.stop()
        try:
            with st.spinner("Extracting chat and images from ZIP…"):
                chat_bytes, image_map = zip_extractor.extract(file_bytes)
        except ValueError as e:
            st.error(str(e))
            st.stop()
        cache_bytes = file_bytes  # cache key uses original ZIP bytes
    else:
        _MAX_TXT_BYTES = 5 * 1024 * 1024
        if len(file_bytes) > _MAX_TXT_BYTES:
            st.error(
                f"File is {len(file_bytes) / 1024 / 1024:.1f} MB — limit is 5 MB. "
                "Export a smaller date range from WhatsApp."
            )
            st.stop()
        chat_bytes = file_bytes
        cache_bytes = file_bytes

    try:
        cached_data, cache_key = cache.load(cache_bytes)
    except Exception as e:
        st.warning(f"Cache error: {e}. Running fresh analysis.")
        cached_data, cache_key = None, cache._key(cache_bytes)

    if cached_data:
        st.session_state["data"] = cached_data
        st.session_state["alias_map"] = cached_data.get("alias_map", {})
        st.session_state["cache_status"] = "Using cached analysis"
    else:
        st.session_state["cache_status"] = "Running fresh analysis…"
        with st.spinner("Parsing chat…"):
            messages, alias_map = parser.parse(chat_bytes)
            st.session_state["alias_map"] = alias_map

        with st.spinner(f"Analyzing {len(messages)} messages with AI (may take a minute)…"):
            try:
                raw = extractor.extract(messages)
            except ValueError as e:
                st.error(str(e))
                st.stop()

        with st.spinner("Building dashboard…"):
            data = aggregator.build(raw)

        with st.spinner("Fetching movie data from TMDB…"):
            canonical_titles = [m["title"] for m in data["movies"]]
            tmdb_data = enricher.enrich(canonical_titles)
            aggregator.attach_tmdb(data["movies"], tmdb_data)

        with st.spinner("Generating opinion summaries…"):
            summarizer.summarize(data["movies"])

        if image_map:
            with st.spinner(f"Analyzing {len(image_map)} images with AI…"):
                message_links = {
                    m["media_filename"]: {
                        "sender": m["sender"],
                        "text": m["text"],
                        "timestamp": str(m["timestamp"]) if m.get("timestamp") else None,
                    }
                    for m in messages
                    if m.get("media_filename")
                }
                try:
                    img_analysis = image_analyzer.analyze(image_map, message_links)

                    # Enrich any new movies discovered from images that aren't in the text extraction
                    existing_titles = {m["title"] for m in data["movies"]}
                    new_titles = [
                        t for t in {r["movie_title"] for r in img_analysis.values() if r.get("movie_title")}
                        if t and t not in existing_titles
                    ]
                    if new_titles:
                        new_tmdb = enricher.enrich(new_titles)
                        for title in new_titles:
                            data["movies"].append({
                                "title": title,
                                "tmdb": new_tmdb.get(title, enricher.empty_tmdb()),
                                "group_sentiment": "neutral",
                                "group_sentiment_score": 0.5,
                                "mention_count": 0,
                                "recommendations": 0,
                                "avoid_signals": 0,
                                "explicit_ratings": [],
                                "per_person": {},
                                "first_mentioned_at": None,
                                "timeline": [],
                                "shared_images": [],
                                "opinion_summary": None,
                            })

                    aggregator.attach_images(data, img_analysis, image_map)
                except Exception as e:
                    st.warning(f"Image analysis failed: {e}. Continuing without media.")
                    data["image_analysis"] = {"total_images": 0, "linked": 0, "unlinked": 0}
                    for m in data["movies"]:
                        m.setdefault("shared_images", [])
                    data["unlinked_images"] = []
        else:
            data["image_analysis"] = {"total_images": 0, "linked": 0, "unlinked": 0}
            for m in data["movies"]:
                m.setdefault("shared_images", [])
            data.setdefault("unlinked_images", [])

        data["alias_map"] = alias_map
        cache.save(cache_key, data)
        if name := session_name_input.strip():
            sessions.register(name, cache_key, len(data["movies"]), user_id)
        st.session_state["data"] = data
        st.session_state["cache_status"] = "Fresh analysis complete — cached for next time"

# ── Dashboard ─────────────────────────────────────────────────────────────────

if "data" not in st.session_state:
    st.title("movieWiz")
    st.markdown(
        "Upload a WhatsApp chat export (.txt) from the sidebar and click **Analyze Chat** to get started."
    )
    st.stop()

data = st.session_state["data"]
movies = data.get("movies", [])
people = data.get("people", {})
actors = data.get("actors_directors", [])

if not movies:
    st.warning("No movies were found in this chat. Try a different export.")
    st.stop()

tab1, tab2, tab4, tab5, tab6 = st.tabs(
    ["Overview", "Movie Explorer", "Sentiment Deep Dive", "Timeline", "Actors & Directors"]
)

# ── Tab 1: Overview ───────────────────────────────────────────────────────────

with tab1:
    st.header("Overview")

    top_movie = movies[0]["title"] if movies else "—"
    top_person = max(people, key=lambda p: people[p]["total_movie_messages"], default="—")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Movies Discussed", len(movies))
    col2.metric("People in Chat", len(people))
    col3.metric("Most Discussed", top_movie)
    col4.metric("Most Active", top_person)

    if alias_map := st.session_state.get("alias_map", {}):
        with st.expander(f"{len(alias_map)} phone number(s) anonymised"):
            for num, label in alias_map.items():
                st.caption(f"{label} — {num}")

    st.subheader("Top Movies by Mention Count")
    top_n = movies[:15]
    fig = px.bar(
        x=[m["mention_count"] for m in top_n],
        y=[m["title"] for m in top_n],
        orientation="h",
        color=[m["group_sentiment"] for m in top_n],
        color_discrete_map={"positive": "#4CAF50", "mixed": "#FF9800", "negative": "#F44336"},
        labels={"x": "Mentions", "y": "Movie"},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=400)
    st.plotly_chart(fig, use_container_width=True)

    if people:
        st.subheader("Top Contributors")
        df_contrib = pd.DataFrame(
            [
                {
                    "Person": p,
                    "Movie Messages": d["total_movie_messages"],
                    "Movies Mentioned": len(d["movies_mentioned"]),
                    "Recommendations": d["recommendation_count"],
                    "Avg Sentiment": round(
                        sum(d["sentiment_scores"]) / len(d["sentiment_scores"]), 2
                    ) if d["sentiment_scores"] else "—",
                }
                for p, d in people.items()
            ]
        ).sort_values("Movie Messages", ascending=False)
        st.dataframe(df_contrib, use_container_width=True, hide_index=True)

# ── Tab 2: Movie Explorer ─────────────────────────────────────────────────────

with tab2:
    st.header("Movie Explorer")

    cols = st.columns(3)
    for i, movie in enumerate(movies):
        with cols[i % 3]:
            tmdb = movie.get("tmdb", {})
            poster = tmdb.get("poster_url")
            if poster:
                st.image(poster, width=200)
            else:
                st.markdown("🎬 *No poster*")

            st.markdown(f"**{movie['title']}**")
            if tmdb.get("year"):
                st.caption(f"{tmdb['year']} · {', '.join(tmdb.get('genres', []))}")
            if tmdb.get("tmdb_score"):
                st.caption(f"TMDB: ⭐ {tmdb['tmdb_score']}")

            badge = _SENTIMENT_BADGE.get(movie["group_sentiment"], "")
            st.caption(f"Group: {badge}  ·  {movie['mention_count']} mentions")

            if movie["explicit_ratings"]:
                st.caption("Ratings: " + ", ".join(movie["explicit_ratings"]))

            with st.expander("Per-person opinions"):
                for person, pdata in movie["per_person"].items():
                    rating_str = f" ({pdata['rating']})" if pdata.get("rating") else ""
                    st.markdown(f"**{person}**{rating_str}")
                    if summary := pdata.get("summary"):
                        st.markdown(summary)
                    if pdata.get("quotes"):
                        with st.expander("Raw quotes", expanded=False):
                            for q in pdata["quotes"][:3]:
                                st.markdown(f"> *{q}*")

            st.divider()

# ── Tab 4: Sentiment Deep Dive ────────────────────────────────────────────────

with tab4:
    st.header("Sentiment Deep Dive")

    sentiment_data = []
    for movie in movies:
        pos = sum(1 for p in movie["per_person"].values() if p.get("sentiment") == "positive")
        neg = sum(1 for p in movie["per_person"].values() if p.get("sentiment") == "negative")
        mix = sum(1 for p in movie["per_person"].values() if p.get("sentiment") == "mixed")
        sentiment_data.append(
            {
                "Movie": movie["title"],
                "Positive": pos,
                "Mixed": mix,
                "Negative": neg,
                "Score": movie["group_sentiment_score"],
                "Mentions": movie["mention_count"],
                "Recommended by": movie["recommendations"],
            }
        )

    df_sent = pd.DataFrame(sentiment_data).sort_values("Score", ascending=False)

    fig4 = go.Figure()
    for col, color in [("Positive", "#4CAF50"), ("Mixed", "#FF9800"), ("Negative", "#F44336")]:
        fig4.add_trace(
            go.Bar(name=col, x=df_sent["Movie"], y=df_sent[col], marker_color=color)
        )
    fig4.update_layout(barmode="stack", title="Sentiment Distribution per Movie", height=400)
    st.plotly_chart(fig4, use_container_width=True)

    st.subheader("Movie Summary Table")
    st.dataframe(
        df_sent[["Movie", "Score", "Mentions", "Recommended by", "Positive", "Mixed", "Negative"]],
        use_container_width=True,
    )

# ── Tab 5: Timeline ───────────────────────────────────────────────────────────

with tab5:
    st.header("Discussion Timeline")

    timeline_rows = []
    for movie in movies:
        for event in movie["timeline"]:
            ts = event.get("timestamp")
            if ts:
                timeline_rows.append(
                    {
                        "timestamp": ts,
                        "Movie": movie["title"],
                        "Sender": event.get("sender", ""),
                        "Sentiment": event.get("sentiment", "neutral"),
                    }
                )

    if not timeline_rows:
        st.info("No timeline data available (timestamps may be missing).")
    else:
        df_timeline = pd.DataFrame(timeline_rows)
        df_timeline["timestamp"] = pd.to_datetime(df_timeline["timestamp"], errors="coerce")
        df_timeline = df_timeline.dropna(subset=["timestamp"])

        fig5 = px.scatter(
            df_timeline,
            x="timestamp",
            y="Movie",
            color="Movie",
            hover_data=["Sender", "Sentiment"],
            title="When Each Movie Was Discussed",
            height=max(400, len(movies) * 30),
        )
        fig5.update_traces(marker_size=10)
        st.plotly_chart(fig5, use_container_width=True)

        st.subheader("Discussion Density Over Time")
        df_grouped = (
            df_timeline.set_index("timestamp")
            .groupby([pd.Grouper(freq="D"), "Movie"])
            .size()
            .reset_index(name="count")
        )
        if not df_grouped.empty:
            fig6 = px.line(
                df_grouped,
                x="timestamp",
                y="count",
                color="Movie",
                title="Daily Movie Mentions",
            )
            st.plotly_chart(fig6, use_container_width=True)

# ── Tab 6: Actors & Directors ─────────────────────────────────────────────────

with tab6:
    st.header("Actors & Directors")

    if not actors:
        st.info("No actors or directors were mentioned in this chat.")
    else:
        df_actors = pd.DataFrame([
            {
                "Name": a["name"],
                "Role": a["role"].capitalize(),
                "Mentioned By": ", ".join(a["mentioned_by"]),
                "Movies": ", ".join(a["associated_movies"]),
            }
            for a in actors
        ])
        st.dataframe(df_actors, use_container_width=True)

        st.subheader("Quotes")
        for a in actors:
            if a["contexts"]:
                with st.expander(f"{a['name']} ({a['role']})"):
                    for ctx in a["contexts"]:
                        st.markdown(f"> *{ctx}*")
