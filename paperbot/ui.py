import uvicorn
import threading
import webbrowser

from paperbot.gui.app import app

def _open_app_window(url: str) -> None:
    """Open the app window."""
    webbrowser.open(url)
    
def run_ui() -> None:
    """Main entry point for UI."""
    host, port = "127.0.0.1", 8001
    url = f"http://{host}:{port}"

    threading.Timer(0.8, lambda: _open_app_window(url)).start()
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False,
        access_log=False
    )