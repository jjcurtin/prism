"""task for running an R script within the PRISM framework"""

import subprocess, os
from system_tasks._system_task import SystemTask
from _types import App

# Dev's own commit ce3aeaa bounded the SMS send (SMS_SEND_TIMEOUT_SECONDS,
# _helper.py) and the research-drive mount probe (DRIVE_CHECK_TIMEOUT_SECONDS,
# _check_system.py) for exactly the reason this bounds the R subprocess too:
# a single blocking call freezes the whole single-threaded SystemTaskManager
# pipeline -- every other scheduled system task stops until it resolves.
# 3 hours (not a short bound like the other two): real R scripts on this
# platform legitimately run long. This is a safety net against a truly
# hung process, not a performance target.
R_SCRIPT_TIMEOUT_SECONDS = 10800

class RunRScript(SystemTask):
    def __init__(self, app: App, r_script_path: str) -> None:
        super().__init__(app)
        self.r_script_path = r_script_path

    def run(self) -> int:
        """Refuses to execute if `r_script_path` resolves (via realpath)
        outside `scripts_dir` -- guards against a path-traversal-style script
        path (e.g. "../../etc/whatever") escaping the sandboxed R scripts
        directory.

        Passes `cwd=scripts_dir` to subprocess.run rather than os.chdir-ing
        this process into scripts_dir and back around the call (the old
        approach): os.chdir is process-global, and this task can run
        concurrently with other threads that resolve their own relative
        paths (the Flask handler serving
        /system/execute_r_script_task/<path>, the scheduler's own
        background thread) -- a window existed where those could observe
        the wrong cwd. cwd= only affects the spawned subprocess, not this
        process, so the hazard doesn't exist to narrow, only to remove.
        """
        self.task_type = f"RUN_R_SCRIPT (script path: {self.r_script_path})"
        self.app.add_to_transcript(f"{self.task_type} #{self.task_number} initiated.")
        scripts_dir = self.app.r_scripts_dir
        if not os.path.exists(scripts_dir):
            self.app.add_to_transcript(f"Scripts directory {scripts_dir} does not exist. Please check the path.", "ERROR")
            return 1
        script_full_path = os.path.join(scripts_dir, self.r_script_path)
        if not os.path.exists(script_full_path):
            self.app.add_to_transcript(f"R script {self.r_script_path} does not exist in {scripts_dir}. Please check the path.", "ERROR")
            return 1
        resolved_script = os.path.realpath(script_full_path)
        resolved_scripts_dir = os.path.realpath(scripts_dir)
        if os.path.commonpath([resolved_script, resolved_scripts_dir]) != resolved_scripts_dir:
            self.app.add_to_transcript(f"R script path {self.r_script_path} escapes the scripts directory {scripts_dir}. Refusing to run.", "ERROR")
            return 1
        try:
            result = subprocess.run(
                ['Rscript', self.r_script_path], capture_output = True, text = True,
                cwd = scripts_dir, timeout = R_SCRIPT_TIMEOUT_SECONDS,
            )
            if result.returncode != 0:
                self.app.add_to_transcript(f"R script failed to run {self.r_script_path}. Error message: {result.stderr.strip()}", "ERROR")
                return 1
            self.app.add_to_transcript(f"{self.task_type} #{self.task_number} script run complete. Output: {result.stdout.strip()}", "SUCCESS")
            return 0
        except subprocess.TimeoutExpired:
            self.app.add_to_transcript(
                f"ERROR: {self.task_type} #{self.task_number} did not finish within "
                f"{R_SCRIPT_TIMEOUT_SECONDS}s and was killed -- the script may be hung; check it manually.",
                "ERROR",
            )
            return 1
        except FileNotFoundError as e:
            # subprocess.run raises this (not OSError generically) when the
            # executable itself -- 'Rscript', not self.r_script_path, which
            # was already confirmed to exist above -- can't be found on
            # PATH. On Windows this is the well-known R gotcha: installing
            # R doesn't add its bin/ directory (where Rscript.exe lives) to
            # PATH automatically. Named explicitly so this reads as an
            # actionable environment problem, not a generic script failure.
            self.app.add_to_transcript(
                f"ERROR: {self.task_type} #{self.task_number} could not launch the 'Rscript' executable -- "
                f"is R installed on this machine, and is its bin/ directory (containing Rscript.exe) on PATH? "
                f"System error: {e}",
                "ERROR",
            )
            return 1
        except Exception as e:
            self.app.add_to_transcript(f"ERROR: {self.task_type} #{self.task_number} failed to properly run script. Error message: {e}", "ERROR")
            return 1
