import pathlib
import shutil

for d in ("logs/transcripts", "logs/ema_logs", "logs/feedback_logs"):
    pathlib.Path(d).mkdir(parents=True, exist_ok=True)

for pattern in ("api/*.template", "config/*.template"):
    for template in pathlib.Path(".").glob(pattern):
        dest = template.with_suffix("")
        if not dest.exists():
            shutil.copy(template, dest)
