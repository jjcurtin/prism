import pathlib

for d in ("logs/transcripts",):
    pathlib.Path(d).mkdir(parents=True, exist_ok=True)
