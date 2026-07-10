"""Type-only alias for the running `PRISM` application instance (see
run_prism.py), threaded through _helper.py, _routes.py, task_managers/, and
system_tasks/ as `app`/`app_instance`.

Imported only under TYPE_CHECKING (never evaluated at runtime) so those
modules don't need a real import of run_prism.py -- run_prism.py itself
imports _routes.py and task_managers/ at runtime, so a real top-of-file
import back here would be circular. At runtime `App` is just `object`; it's
never used for isinstance checks or anything else that would care.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from run_prism import PRISM as App
else:
    App = object
