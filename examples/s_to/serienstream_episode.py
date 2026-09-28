from h0melab.config import Audio, Subtitles
from h0melab.models import SerienstreamEpisode

episode_url = "https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-1"

episode = SerienstreamEpisode(episode_url)

print("=== EPISODE INFO ===")
print("URL:", episode.url)
print("Title DE:", episode.title_de)
print("Title EN:", episode.title_en)
print("Episode Number:", episode.episode_number)
print("Provider Data:", episode.provider_data)
print("Selected Path:", episode.selected_path)
print("Selected Language:", episode.selected_language)
print("Selected Provider:", episode.selected_provider)
print("Redirect URL:", episode.redirect_url)
print("Provider URL:", episode.provider_url)
print("Stream URL:", episode.stream_url)
print("Base Folder:", episode._base_folder)
print("Folder Path:", episode._folder_path)
print("File Name:", episode._file_name)
print("File Extension:", episode._file_extension)
print("Episode Path:", episode._episode_path)
print("Is Downloaded:", episode.is_downloaded)
print()

print("=== SERIES INFO ===")
print("Title:", episode.series.title)
print()

print("=== SEASON INFO ===")
print("Season URL:", episode.season.url)
print()

print("=== CUSTOM PROVIDER LINK ===")
language = (Audio.GERMAN, Subtitles.NONE)
provider = "VOE"

provider_link = episode.provider_link(language=language, provider=provider)
print("Provider Link:", provider_link)

# episode.download()
# episode.watch()
# episode.syncplay()
