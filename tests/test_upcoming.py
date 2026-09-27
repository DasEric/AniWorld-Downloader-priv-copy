"""Upcoming watchlist validation, matching and secret-safe TMDB failures."""

from types import SimpleNamespace

from aniworld.web import db, tmdb, upcoming

MOVIE = {
    "tmdb_id": 42,
    "title": "Future Film",
    "original_title": "Future Film",
    "release_date": "2999-01-01",
    "release_year": 2999,
    "poster_path": "/poster.jpg",
    "overview": "Soon",
}


def test_upcoming_page_uses_the_same_layout_language_as_autosync(client):
    page = client.get("/upcoming")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'class="container container-narrow"' in html
    assert 'class="page-head"' in html
    assert 'class="data-table stacked-table"' in html
    assert 'class="sync-stats"' in html


def test_tmdb_http_error_does_not_leak_v3_key(monkeypatch):
    secret = "1234567890abcdef1234567890abcdef"
    monkeypatch.setenv("ANIWORLD_TMDB_API_KEY", secret)
    response = SimpleNamespace(status_code=500)
    monkeypatch.setattr(tmdb.requests, "get", lambda *args, **kwargs: response)

    try:
        tmdb.search_movies("film")
    except tmdb.TMDBError as exc:
        assert secret not in str(exc)
        assert str(exc) == "TMDB request failed (500)"
    else:
        raise AssertionError("TMDBError was not raised")


def test_upcoming_api_never_returns_tmdb_key(client, monkeypatch):
    secret = "secret-key"
    monkeypatch.setenv("ANIWORLD_TMDB_API_KEY", secret)
    payload = client.get("/api/upcoming").get_json()
    assert payload["configured"] is True
    assert secret not in str(payload)


def test_add_pause_resume_and_prevent_finished_requeue(client, monkeypatch):
    monkeypatch.setattr(tmdb, "movie_details", lambda _movie_id: dict(MOVIE))
    added = client.post("/api/upcoming", json={"tmdb_id": 42})
    assert added.status_code == 201
    movie_id = added.get_json()["id"]

    assert (
        client.patch(f"/api/upcoming/{movie_id}", json={"status": "paused"}).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/upcoming/{movie_id}", json={"status": "waiting"}
        ).status_code
        == 200
    )
    db.update_upcoming_movie(movie_id, status="downloaded")
    assert (
        client.patch(f"/api/upcoming/{movie_id}", json={"status": "paused"}).status_code
        == 409
    )


def test_multiple_verified_sites_choose_priority_instead_of_stalling(monkeypatch):
    movie = {**MOVIE, "release_date": "2000-01-01", "release_year": 2000}
    monkeypatch.setattr(upcoming.settings_store, "site_enabled", lambda _site: True)
    monkeypatch.setattr(upcoming.sitesearch, "MOVIE_SITES", ("megakino", "filmo"))
    monkeypatch.setattr(
        upcoming.sitesearch,
        "search",
        lambda site, _title: [
            {"title": "Future Film", "url": f"https://{site}.example/movie"}
        ],
    )
    provider = SimpleNamespace(
        series_cls=lambda url: SimpleNamespace(release_year="2000")
    )
    monkeypatch.setattr("aniworld.providers.resolve_provider", lambda _url: provider)

    assert upcoming._exact_hit(movie)["url"] == "https://megakino.example/movie"


def test_non_latin_titles_do_not_match_only_because_normalisation_is_empty(monkeypatch):
    movie = {
        **MOVIE,
        "title": "日本映画",
        "original_title": "日本映画",
        "release_year": 2000,
    }
    monkeypatch.setattr(upcoming.settings_store, "site_enabled", lambda _site: True)
    monkeypatch.setattr(upcoming.sitesearch, "MOVIE_SITES", ("megakino",))
    monkeypatch.setattr(
        upcoming.sitesearch,
        "search",
        lambda _site, _title: [
            {"title": "한국 영화", "url": "https://megakino.example/wrong"}
        ],
    )
    provider = SimpleNamespace(
        series_cls=lambda url: SimpleNamespace(release_year="2000")
    )
    monkeypatch.setattr("aniworld.providers.resolve_provider", lambda _url: provider)

    assert upcoming._exact_hit(movie) is None
