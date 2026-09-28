from h0melab.models import SerienstreamSeason

season_url = "https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1"

season = SerienstreamSeason(season_url)

print("=== SEASON INFO ===")
print("URL:", season.url)
print("Season Number:", season.season_number)
print("Episode Count:", season.episode_count)
print("Episodes:", season.episodes)
print()

print("=== SERIES INFO ===")
print("Title:", season.series.title)
print()

# season.download()
# season.watch()
# season.syncplay()
