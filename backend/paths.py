"""Read-only application resources and writable per-user application data."""
import os
from pathlib import Path
import sys


def resource_root():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


ROOT = resource_root()


def runtime_dir():
    if getattr(sys, "frozen", False):
        executable=Path(sys.executable).resolve()
        # Bind an installed entry to its own data even when launched from a
        # packaged desktop host whose AppData writes are Windows-redirected.
        if executable.parent.name.lower()=='app' and executable.parent.parent.name=='PhotoshopMenu':
            return executable.parent.parent
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "PhotoshopMenu"
    return ROOT / ".runtime"


def overlay_command(url, token, runtime):
    root = resource_root()
    return [str(root / 'native/MenuHost.exe'), '--parent', str(os.getpid()),
            '--icon', str(root / 'frontend/public/icon.ico')]
