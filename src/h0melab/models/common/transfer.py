"""Fast resilient transfer fallback powered by yt-dlp."""

from pathlib import Path


class TransferUnavailable(RuntimeError):
    pass


_AUDIO_LANG_PREFIXES = {
    "deu": ("de", "ger", "deu", "German"),
    "eng": ("en", "eng", "English"),
    "jpn": ("ja", "jp", "jpn", "Japanese"),
}


def _format_selector(preferred_audio_lang):
    """Prefer the requested HLS audio rendition, then fall back safely."""
    base = "bestvideo+bestaudio/best"
    prefixes = _AUDIO_LANG_PREFIXES.get(preferred_audio_lang, ())
    if not prefixes:
        return base
    preferred = [f"bestvideo+bestaudio[language^={prefix}]" for prefix in prefixes]
    return "/".join((*preferred, base))


def download_with_ytdlp(
    url,
    output_path,
    headers,
    concurrency,
    progress_hook,
    preferred_audio_lang=None,
):
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise TransferUnavailable("yt-dlp is not installed") from exc

    output_path = Path(output_path)
    from ...config import DEFAULT_USER_AGENT

    request_headers = {"User-Agent": DEFAULT_USER_AGENT}
    request_headers.update(headers or {})
    options = {
        "outtmpl": str(output_path),
        "format": _format_selector(preferred_audio_lang),
        "merge_output_format": output_path.suffix.lstrip(".") or "mkv",
        "http_headers": request_headers,
        "concurrent_fragment_downloads": max(1, int(concurrency)),
        "fragment_retries": 10,
        "retries": 5,
        "socket_timeout": 30,
        "http_chunk_size": 10 * 1024 * 1024,
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "keepvideo": False,
        "nopart": False,
        "continuedl": True,
        "overwrites": True,
    }
    with YoutubeDL(options) as downloader:
        code = downloader.download([url])
    if code or not output_path.exists() or output_path.stat().st_size == 0:
        raise TransferUnavailable("yt-dlp did not produce the requested file")
    return output_path
