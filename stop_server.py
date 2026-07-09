import subprocess
import sys
import time

if sys.platform == "win32":
    subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_prism.py' } "
            "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }",
        ],
        check=False,
    )
else:
    subprocess.run(["pkill", "-f", "run_prism.py"], check=False)

time.sleep(1)
