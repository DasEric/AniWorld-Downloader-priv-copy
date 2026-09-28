"""Non-destructive migration coverage for the v2 product transition."""

import sqlite3
from pathlib import Path

from dotenv import dotenv_values

from aniworld import env
from aniworld.web import db


def test_v1_environment_directory_and_unknown_values_are_preserved(
    tmp_path, monkeypatch
):
    home = tmp_path / "home"
    legacy = home / ".aniworld"
    target = home / ".h0melab-downloader"
    legacy.mkdir(parents=True)
    (legacy / ".env").write_text(
        "ANIWORLD_INSTALL_FOLDER=.aniworld\n"
        "ANIWORLD_LANGUAGE='German Dub'\n"
        "CUSTOM_DEPLOYMENT_VALUE=kept\n",
        encoding="utf-8",
    )
    (legacy / "custom.css").write_text("/* keep */", encoding="utf-8")
    example = tmp_path / ".env.example"
    example.write_text(
        "H0MELAB_INSTALL_FOLDER=.h0melab-downloader\nH0MELAB_LANGUAGE='German Dub'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("H0MELAB_INSTALL_FOLDER", raising=False)
    monkeypatch.delenv("ANIWORLD_INSTALL_FOLDER", raising=False)

    resolved = env.initialize_app_env(example, target)
    values = dotenv_values(target / ".env")

    assert resolved == target.resolve()
    assert values["H0MELAB_LANGUAGE"] == "German Dub"
    assert values["CUSTOM_DEPLOYMENT_VALUE"] == "kept"
    assert Path(values["H0MELAB_INSTALL_FOLDER"]) == target.resolve()
    assert (target / "custom.css").read_text(encoding="utf-8") == "/* keep */"


def test_mounted_v1_volume_is_pinned_to_the_new_mount_path(tmp_path, monkeypatch):
    home = tmp_path / "home"
    target = home / ".h0melab-downloader"
    target.mkdir(parents=True)
    (target / ".env").write_text(
        "ANIWORLD_INSTALL_FOLDER=.aniworld\nANIWORLD_LANGUAGE='German Dub'\n",
        encoding="utf-8",
    )
    example = tmp_path / ".env.example"
    example.write_text(
        "H0MELAB_INSTALL_FOLDER=.h0melab-downloader\nH0MELAB_LANGUAGE='German Dub'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("H0MELAB_INSTALL_FOLDER", raising=False)
    monkeypatch.delenv("ANIWORLD_INSTALL_FOLDER", raising=False)

    assert env.initialize_app_env(example, target) == target.resolve()
    assert (
        Path(dotenv_values(target / ".env")["H0MELAB_INSTALL_FOLDER"])
        == target.resolve()
    )


def test_v1_database_is_backed_up_and_watchlist_rows_migrate_once(
    tmp_path, monkeypatch
):
    legacy = tmp_path / "legacy-v1.db"
    current = tmp_path / "migrated-v2.db"
    connection = sqlite3.connect(legacy)
    connection.execute(
        """
        CREATE TABLE upcoming_movies (
            id INTEGER PRIMARY KEY, tmdb_id INTEGER UNIQUE, title TEXT,
            original_title TEXT DEFAULT '', release_date TEXT, release_year INTEGER,
            poster_path TEXT, overview TEXT DEFAULT '', language TEXT DEFAULT 'German Dub',
            provider TEXT DEFAULT 'VOE', custom_path_id INTEGER, status TEXT DEFAULT 'waiting',
            matched_url TEXT, queue_id INTEGER, last_checked_at TEXT, last_message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        "INSERT INTO upcoming_movies (id, tmdb_id, title, release_date, release_year) VALUES (7, 42, 'Kept', '2020-01-01', 2020)"
    )
    connection.commit()
    connection.close()

    monkeypatch.setattr(db, "LEGACY_DB_PATH", legacy)
    monkeypatch.setattr(db, "DB_PATH", current)
    monkeypatch.setattr(db, "_initialized", False)
    db.init_db()
    assert legacy.exists()
    assert db.get_upcoming_movie(7)["title"] == "Kept"

    db.delete_upcoming_movie(7)
    monkeypatch.setattr(db, "_initialized", False)
    db.init_db()
    assert db.get_upcoming_movie(7) is None
