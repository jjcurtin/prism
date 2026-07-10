"""Type-only alias for the `self` parameter threaded through every
user_interface_menus/ menu function.

These are plain functions taking a `PRISMInterface` instance (see
prism_interface.py) as their first positional argument, not bound methods --
`self` is just this codebase's chosen parameter name for it, not a `class`
method receiver. `Interface` is evaluated only under TYPE_CHECKING (never
imported at runtime), so every menu file can write `self: Interface`
without pulling in prism_interface.py directly at import time --
prism_interface.py imports user_interface_menus._main_menu (transitively
importing the rest of this tree), so a real runtime import back here would
be circular.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from prism_interface import PRISMInterface as Interface
else:
    Interface = object

# A menu-options dict maps a command/index key (e.g. "settings", "3") to
# {"description": <str shown to the user>, "menu_caller": <callable or str
# alias, see goto_menu() in utils/_menu_navigation.py>}. Used throughout
# this tree for both the per-menu `menu_options` built locally in each menu
# function and the global registry built by utils/_commands.py's
# init_commands() (and stored on ui_state.menu_options).
MenuOptions = dict[str, dict[str, Any]]
