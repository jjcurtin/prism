import pathlib

for d in ("logs/transcripts", "logs/ema_logs", "logs/feedback_logs"):
    pathlib.Path(d).mkdir(parents=True, exist_ok=True)
