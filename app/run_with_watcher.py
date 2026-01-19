import os
import sys
from PySide6.QtWidgets import QApplication

from app.memory_store import MemoryStore
from app.controller import Controller

from app.watchers.codex_sessions_watcher import CodexSessionsWatcher, CodexSessionsWatcherConfig


def main():
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
    store = MemoryStore()
    cfg = store.load()
    controller = Controller(cfg, store)
    app._controller = controller

    def on_new(text, html):
        # HTML not needed for now (kept for compatibility with existing watcher signature)
        # Passe par un signal Qt pour basculer sur le thread UI.
        controller.newMessageRequested.emit(text)

    # Read Codex transcripts from disk (~/.codex/sessions/.../rollout-*.jsonl)
    sessions_watcher = CodexSessionsWatcher(
        CodexSessionsWatcherConfig(),
        on_new_message=on_new,
        log=print,
    )
    sessions_watcher.start()
    app._sessions_watcher = sessions_watcher

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
