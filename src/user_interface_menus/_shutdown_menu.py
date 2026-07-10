"""self explanatory"""

import time

from user_interface_menus._menu_helper import *
from user_interface_menus._types import Interface

def shutdown_menu(self: Interface) -> None:
    ok, _ = self.api("GET", "system/uptime")
    if ok:
        if prompt_confirmation(self, "Are you sure you want to shut down PRISM?"):
            # The server's shutdown handler calls os._exit(0) from inside the
            # request handler itself, so it almost never gets to send this
            # POST's own HTTP response back -- self.api() sees that as a
            # connection error (ok=False) even on a fully successful
            # shutdown. Don't trust this call's own return value; instead,
            # give the process a moment to actually exit and then re-probe
            # reachability, which is what actually distinguishes "shut down
            # successfully" (now unreachable) from "shutdown failed" (still
            # reachable).
            try:
                self.api("POST", "system/shutdown")
                time.sleep(1)
                still_up, _ = self.api("GET", "system/uptime")
                if not still_up:
                    success("PRISM shut down.")
                    exit(0)
                else:
                    error("Failed to shut down PRISM.")
            except Exception as e:
                error(f"Error: {e}")
        else:
            print("Shutdown cancelled.")
    else:
        success("PRISM is already shut down.")