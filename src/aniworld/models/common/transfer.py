"""Fast resilient transfer fallback powered by yt-dlp."""

from pathlib import Path


class TransferUnavailable(RuntimeError):
    pass


def download_with_ytdlp(url, output_path, headers, concurrency, progress_hook):
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise TransferUnavailable("yt-dlp is not installed") from exc

    output_path = Path(output_path)
    options = {
        "outtmpl": str(output_path),
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": output_path.suffix.lstrip(".") or "mkv",
        "http_headers": dict(headers or {}),
        "concurrent_fragment_downloads": max(1, int(concurrency)),
        "fragment_retries": 10,
        "retries": 10,
        "socket_timeout": 30,
        "http_chunk_size": 10 * 1024 * 1024,
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nopart": True,
        "overwrites": True,
    }
    with YoutubeDL(options) as downloader:
        code = downloader.download([url])
    if code or not output_path.exists() or output_path.stat().st_size == 0:
        raise TransferUnavailable("yt-dlp did not produce the requested file")
    return output_path
