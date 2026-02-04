"""Entry point for running paperbot as a module or installed script.

Usage:
    paperbot / python -m paperbot         → GUI (streamlit run)
    paperbot <command> ... / python -m paperbot <command> ... → CLI
"""

import atexit
import sys
import uvicorn
import threading
import webbrowser


def _reset_picked_on_exit() -> None:
    """Reset all is_picked to 0 when the process exits."""
    try:
        from paperbot.config import Settings
        from paperbot.database.repository import PaperRepository
        settings = Settings.load()
        repo = PaperRepository(settings.db_path)
        repo.reset_all_picked()
    except Exception:
        pass  # avoid breaking process exit

def _open_app_window(url: str) -> None:
    """Open the app window."""
    webbrowser.open(url)

def run() -> None:
    """Entry point: no args → GUI (via streamlit run), else → CLI."""
    host, port = "127.0.0.1", 8000
    url = f"http://{host}:{port}"
        
    atexit.register(_reset_picked_on_exit)
    threading.Timer(0.8, lambda: _open_app_window(url)).start()
    if len(sys.argv) == 1:
        uvicorn.run(
            "paperbot.gui.app:app",
            host=host,
            port=port,
            reload=False,
            access_log=False
        )
    else:
        from paperbot.cli import run_cli
        run_cli()


if __name__ == "__main__":
    run()
