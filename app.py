import os
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from dotenv import load_dotenv

import cache
import parser
import extractor
import enricher
import aggregator

load_dotenv()

st.set_page_config(
    page_title="movieWiz",
    page_icon="🎬",
    layout="wide",
)

# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("movieWiz")
    st.caption("WhatsApp chat movie analyzer")

    uploaded_file = st.file_uploader("Upload WhatsApp chat export (.txt)", type=["txt"])

    anthropic_key = st.text_input(
        "Anthropic API Key",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Required for LLM extraction",
    )
    tmdb_key = st.text_input(
        "TMDB API Key",
        value=os.getenv("TMDB_API_KEY", ""),
        type="password",
        help="Required for movie posters and metadata",
    )

    analyze_btn = st.button("Analyze Chat", type="primary", disabled=uploaded_file is None)

    if "cache_status" in st.session_state:
        st.caption(st.session_state["cache_status"])

# ── Run pipeline ─────────────────────────────────────────────────────────────

if analyze_btn and uploaded_file is not None:
    if anthropic_key:
        os.environ["ANTHROPIC_API_KEY"] = anthropic_key
    if tmdb_key:
        os.environ["TMDB_API_KEY"] = tmdb_key

    file_bytes = uploaded_file.read()

    cached_data, cache_key = cache.load(file_bytes)

    if cached_data:
        st.session_state["data"] = cached_data
        st.session_state["cache_status"] = "Using cached analysis"
    else:
        st.session_state["cache_status"] = "Running fresh analysis…"
        with st.spinner("Parsing chat…"):
            messages = parser.parse(file_bytes)

        with st.spinner(f"Analyzing {len(messages)} messages with AI (may take a minute)…"):
            try:
                raw = extractor.extract(messages)
            except ValueError as e:
                st.error(str(e))
                st.stop()

        unique_titles = list({m["title"] for m in raw["movies"] if m.get("title")})

        with st.spinner("Fetching movie data from TMDB…"):
            tmdb_data = enricher.enrich(unique_titles)

        with st.spinner("Building dashboard…"):
            data = aggregator.build(raw, tmdb_data)

        cache.save(cache_key, data)
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

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Overview", "Movie Explorer", "Who Talks Most", "Sentiment Deep Dive", "Timeline"]
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

# ── Tab 2: Movie Explorer ─────────────────────────────────────────────────────

with tab2:
    st.header("Movie Explorer")

    _SENTIMENT_BADGE = {
        "positive": "🟢 Positive",
        "mixed": "🟡 Mixed",
        "negative": "🔴 Negative",
    }

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
                    quotes = pdata.get("quotes", [])
                    rating = pdata.get("rating", "")
                    rating_str = f" ({rating})" if rating else ""
                    st.markdown(f"**{person}**{rating_str}: {pdata.get('sentiment', '—')}")
                    for q in quotes[:3]:
                        st.markdown(f"> *{q}*")

            st.divider()

# ── Tab 3: Who Talks Most ─────────────────────────────────────────────────────

with tab3:
    st.header("Who Talks About Movies Most")

    if not people:
        st.info("No people data available.")
    else:
        df_people = pd.DataFrame(
            [
                {
                    "Person": p,
                    "Movie Messages": d["total_movie_messages"],
                    "Movies Mentioned": len(d["movies_mentioned"]),
                }
                for p, d in people.items()
            ]
        ).sort_values("Movie Messages", ascending=False)

        fig2 = px.bar(
            df_people,
            x="Person",
            y="Movie Messages",
            color="Movies Mentioned",
            color_continuous_scale="Blues",
            title="Movie-Related Messages per Person",
        )
        st.plotly_chart(fig2, use_container_width=True)

        st.subheader("Movies Mentioned per Person")
        fig3 = px.bar(
            df_people,
            x="Person",
            y="Movies Mentioned",
            title="Unique Movies Each Person Discussed",
        )
        st.plotly_chart(fig3, use_container_width=True)

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
