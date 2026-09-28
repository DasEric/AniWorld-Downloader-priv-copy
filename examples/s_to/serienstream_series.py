from h0melab.models import SerienstreamSeries

series_url = (
    "https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir"
)

series = SerienstreamSeries(series_url)

print("=== SERIES INFO ===")
print("URL:", series.url)
print("Title:", series.title)
print("Title Clean:", series.title_cleaned)
print("Description:", series.description)
print("Genres:", series.genres)
print("Release year:", series.release_year)
print("Poster URL:", series.poster_url)
print("Directors:", series.directors)
print("Actors:", series.actors)
print("Producer:", series.producer)
print("Country:", series.country)
print("Age rating:", series.age_rating)
print("IMDB ID:", series.imdb)
print("Seasons:", series.seasons)
print("Number of seasons:", series.season_count)
print()

# series.download()
# series.watch()
# series.syncplay()
