import os

from h0melab.models import AniworldEpisode

episode = AniworldEpisode(
    "https://aniworld.to/anime/stream/highschool-dxd/staffel-1/episode-1"
)

# Enable AniSkip feature
os.environ["H0MELAB_ANISKIP"] = "1"

# Watch the episode with AniSkip enabled
episode.watch()
