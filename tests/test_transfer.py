"""yt-dlp transfer options without contacting a network."""

import sys
from pathlib import Path
from types import SimpleNamespace

from aniworld.models.common.transfer import download_with_ytdlp


def test_ytdlp_uses_requested_fragment_concurrency(monkeypatch, tmp_path):
    seen = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            seen.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, urls):
            seen["urls"] = urls
            Path(seen["outtmpl"]).write_bytes(b"media")
            return 0

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    output = tmp_path / "episode.mkv"
    result = download_with_ytdlp(
        "https://cdn.example/video.m3u8",
        output,
        {"Referer": "https://source.example/"},
        10,
        lambda _data: None,
    )

    assert result == output
    assert seen["concurrent_fragment_downloads"] == 10
    assert seen["fragment_retries"] == 10
    assert seen["http_chunk_size"] == 10 * 1024 * 1024
    assert seen["nopart"] is True
    assert seen["http_headers"]["Referer"] == "https://source.example/"
