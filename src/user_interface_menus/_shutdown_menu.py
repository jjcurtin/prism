# self explanatory

from user_interface_menus._menu_helper import *

# ------------------------------------------------------------

def shutdown_menu(self):
    if self.api("GET", "system/uptime") is not None:
        if prompt_confirmation(self, "Are you sure you want to shut down PRISM?"):
            try:
                if self.api("POST", "system/shutdown") is not None:
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