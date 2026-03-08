import importlib.util
import os
import shutil
import socket
import subprocess
import sys
from typing import Dict, Optional

from config import DB_PATH


# the `sqlite_web` command comes from the `sqlite-web` package on PyPI.
# wrapping it here allows the main program to start a lightweight browser
# without the caller needing to know the exact command line.

def _which(cmd: str) -> Optional[str]:
    """Return the full path to *cmd* or None if not present."""
    return shutil.which(cmd)


def _sqlite_web_command():
    command_path = _which("sqlite_web")
    if command_path:
        return [command_path], None

    if importlib.util.find_spec("sqlite_web") is not None:
        return [sys.executable, "-m", "sqlite_web"], None

    return None, "sqlite_web command/module not found; install the 'sqlite-web' package"


def _find_free_port(start: int = 8080, end: int = 8090) -> int:
    """Return a port between ``start`` and ``end`` that is not in use.

    Raises ``ValueError`` if no free port is found in the range.
    """
    for port in range(start, end + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
        finally:
            sock.close()
    raise ValueError(f"no free port between {start} and {end}")


def start_sqlite_web(port: Optional[int] = None, readonly: bool = False) -> Dict[str, Optional[str]]:
    """Launch sqlite-web as a background process.

    The ``port`` argument may be ``None`` (the default) in which case the
    function will scan for an available port starting at ``8080``.  A
    ``SQLITE_WEB_PORT`` environment variable may also override the desired
    port.

    Returns a dictionary with keys ``success`` (bool) and one of ``url`` or
    ``message``.  The server is started with :class:`subprocess.Popen` which
    does not block the caller; the caller may keep the returned ``process``
    object if they wish to terminate it later.
    """
    if port is None:
        env = os.environ.get("SQLITE_WEB_PORT")
        if env:
            try:
                port = int(env)
            except ValueError:
                # ignore invalid env value and fall back to scanning
                port = None

    if port is None:
        try:
            port = _find_free_port(8080, 8090)
        except ValueError as exc:
            return {"success": False, "message": str(exc)}

    command, command_error = _sqlite_web_command()
    if command is None:
        return {"success": False, "message": command_error}

    args = list(command) + [DB_PATH, "--port", str(port)]
    if readonly:
        args.append("--readonly")

    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        return {"success": True, "url": f"http://127.0.0.1:{port}", "process": proc}
    except Exception as exc:  # pragma: no cover - rare system error
        return {"success": False, "message": str(exc)}
