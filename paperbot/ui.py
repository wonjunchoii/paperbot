import uvicorn
import threading
import webbrowser

def _open_app_window(url: str) -> None:
    """Open the app window."""
    webbrowser.open(url)
    
def run_ui() -> None:
    """Main entry point for UI."""
    host, port = "127.0.0.1", 8000
    url = f"http://{host}:{port}"

    threading.Timer(0.8, lambda: _open_app_window(url)).start()
    uvicorn.run(
        "paperbot.gui.app:app",
        host=host,
        port=port,
        reload=True,
        access_log=False
    )