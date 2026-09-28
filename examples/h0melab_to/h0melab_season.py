from h0melab.models import AniworldSeason

season_url = "https://aniworld.to/anime/stream/highschool-dxd/staffel-1"

season = AniworldSeason(season_url)

print("=== SEASON INFO ===")
print("URL:", season.url)
print("Are Movies:", season.are_movies)
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
