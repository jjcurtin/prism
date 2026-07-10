"""self explanatory"""

from user_interface_menus._menu_helper import *

def shutdown_menu(self):
    ok, _ = self.api("GET", "system/uptime")
    if ok:
        if prompt_confirmation(self, "Are you sure you want to shut down PRISM?"):
            try:
                shutdown_ok, _ = self.api("POST", "system/shutdown")
                if shutdown_ok:
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