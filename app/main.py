import os
import sys
from PySide6.QtWidgets import QApplication
from .memory_store import MemoryStore
from .controller import Controller

def main() -> int:
    if os.environ.get("CODEXTTS_SILENCE_STDERR", "1") == "1":
        try:
            devnull = open(os.devnull, "w")
            os.dup2(devnull.fileno(), 2)
            sys.stderr = devnull
        except Exception:
            pass
    if "QTWEBENGINE_CHROMIUM_FLAGS" not in os.environ:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
            "--disable-gpu "
            "--disable-gpu-compositing "
            "--disable-software-rasterizer "
            "--disable-logging "
            "--log-level=3"
        )
    if "QTWEBENGINE_DISABLE_GPU" not in os.environ:
        os.environ["QTWEBENGINE_DISABLE_GPU"] = "1"
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    store = MemoryStore()
    cfg = store.load()

    # Keep a strong ref to avoid GC
    app._speachcodexgpt_controller = Controller(cfg, store)

    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
