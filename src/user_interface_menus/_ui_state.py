"""Mutable interface-wide settings and per-menu navigation state.

Deliberately isolated in its own leaf module (no imports of anything else
under user_interface_menus/) rather than living directly in
_menu_helper.py, even though the rest of _menu_helper.py's globals-to-
config-object refactor lives there. Reason: _menu_helper.py's own top of
file does `from user_interface_menus.utils._display import *` (and
transitively _menu_display.py / _menu_navigation.py), and those three
modules each need a live reference to `ui_state` at their own top of file
(so mutations to e.g. `ui_state.color_on` are visible without re-importing
per call, matching every other consumer). If `ui_state` lived in
_menu_helper.py itself, importing it from _display.py's top would create a
real circular import: whichever of {_menu_helper.py, _display.py,
_menu_navigation.py, _menu_display.py} happens to be the *first* one
imported into the process ends up importing the others mid-execution,
before they've finished defining their own names -- confirmed empirically
(`import user_interface_menus.utils._display` as the first import in a
fresh interpreter raised `NameError: name 'yellow' is not defined` while
_menu_helper.py was mid-execution building `read_me_lines`, because
_display.py's own `yellow`/`green`/`red`/etc. hadn't been defined yet at
the point _menu_helper.py's `from ... import *` ran). Since this module has
zero internal dependencies, it can be imported first, last, or anywhere in
between with no ordering hazard.

_menu_helper.py re-exports `ui_state` from here, so
`from user_interface_menus._menu_helper import ui_state` (used by files
loaded well after _menu_helper.py has fully finished initializing, e.g.
settings/_settings_menu.py) keeps working and refers to this exact same
object.
"""

from user_interface_menus._types import MenuOptions

class UIState:
    """Mutable interface-wide settings and per-menu navigation state,
    persisted to config/uiconfig.txt via load_params()/save_params().
    Replaces the old module-level `global` variables -- consuming files
    import this object once at module top instead of re-importing each
    bare setting inside every function body, since mutating
    ui_state.some_attr is visible to every holder of the same object
    reference without needing a fresh import per call.
    """
    def __init__(self) -> None:
        self.window_width: int = 155
        self.window_height: int = 20
        self.right_align: bool = True
        self.related_options_threshold: float = 0.3
        self.best_options_threshold: float = 0.7
        self.assistant_type_speed: float = 0.015
        self.show_readme: bool = True
        self.color_on: bool = True
        self.recent_commands: list[str] = []
        self.menu_delay: float = 0.5
        self.timeout: int = 10
        self.local_menu_options: MenuOptions = {}
        self.current_menu: str | None = None
        self.menu_options: MenuOptions | None = None

ui_state = UIState()
