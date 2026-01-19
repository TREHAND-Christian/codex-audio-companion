from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Any


@dataclass
class CodexSessionsWatcherConfig:
    # Pattern du fichier JSONL (sessions Codex)
    pattern: str = "rollout-*.jsonl"
    poll_interval: float = 0.5  # secondes
    # Lire uniquement la dernière réponse assistant au démarrage (sinon: se placer en fin directement)
    read_last_on_start: bool = True
    # Supprimer les champs TTS du JSONL (nettoyage best-effort)
    scrub_tts_fields: bool = True
    scrub_tts_keys: tuple[str, ...] = (
        "tts",
        "audio",
        "voice",
        "phonemes",
        "timings",
        "durations",
        "audio_url",
        "audio_base64",
    )
    scrub_idle_seconds: float = 1.0
    scrub_min_interval: float = 2.0


class CodexSessionsWatcher:
    """
    Watcher des sessions Codex : lit ~/.codex/sessions/**/rollout-*.jsonl.

    - Au démarrage (ou changement de session), il lit le fichier pour trouver la *dernière*
        réponse assistant et n'émet QUE celle-ci (si read_last_on_start=True).
    - Ensuite il se positionne en fin de fichier et ne lit que les nouvelles lignes.
    """

    def __init__(
        self,
        cfg: Optional[CodexSessionsWatcherConfig] = None,
        on_new_message: Optional[Callable[[str, str], None]] = None,
        log: Callable[[str], None] = print,
    ):
        self.cfg = cfg or CodexSessionsWatcherConfig()
        self.on_new_message = on_new_message
        self.log = log

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._root = self._codex_sessions_root()
        self._current_file: Optional[Path] = None
        self._pos: int = 0

        self._last_emitted_key: str = ""  # anti-doublon
        self._scrub_keys = {k.lower() for k in self.cfg.scrub_tts_keys}
        self._scrub_pending = False
        self._last_scrub_time = 0.0

    def start(self) -> bool:
        if not self._root.exists():
            self.log(f"[sessions] Dossier introuvable: {self._root}")
            return False

        self.log(f"[sessions] Watcher démarré: {self._root}")
        self._thread = threading.Thread(target=self._run, name="CodexSessionsWatcher", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _codex_sessions_root(self) -> Path:
        home = Path(os.environ.get("USERPROFILE") or str(Path.home()))
        return home / ".codex" / "sessions"

    def _find_latest_rollout(self) -> Optional[Path]:
        files = list(self._root.rglob(self.cfg.pattern))
        if not files:
            return None
        return max(files, key=lambda p: p.stat().st_mtime)

    # -------- extraction helpers --------

    def _payload_to_text(self, payload: dict) -> str:
        content = payload.get("content")
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    # cas le plus courant: {"type":"output_text","text":"..."}
                    txt = item.get("text")
                    if isinstance(txt, str):
                        parts.append(txt)
            return "".join(parts).strip()

        return ""

    def _extract_assistant_text(self, obj: dict) -> Optional[tuple[str, str]]:
        """
        Retourne (text, key) si la ligne représente une sortie assistant.
        key sert au dédoublonnage.
        """
        t = obj.get("type") or obj.get("event")
        payload = obj.get("payload")

        # Format observé: {"type":"response_item","payload":{"role":"assistant","content":[{"type":"output_text","text":"..."}]}}
        if t == "response_item" and isinstance(payload, dict):
            if payload.get("role") == "assistant":
                text = self._payload_to_text(payload)
                if text:
                    mid = str(payload.get("id") or obj.get("id") or "")
                    key = mid if mid else f"hash:{hash(text)}"
                    return text, key

        # Fallbacks (formats possibles)
        role = obj.get("role") or obj.get("author")
        if role == "assistant":
            content = obj.get("content")
            if isinstance(content, str) and content.strip():
                text = content.strip()
                key = str(obj.get("id") or f"hash:{hash(text)}")
                return text, key

        msg = obj.get("message")
        if isinstance(msg, dict):
            r = msg.get("role") or msg.get("author")
            if r == "assistant":
                c = msg.get("content")
                if isinstance(c, str) and c.strip():
                    text = c.strip()
                    key = str(msg.get("id") or obj.get("id") or f"hash:{hash(text)}")
                    return text, key

        return None

    # -------- scrubbing helpers --------

    def _scrub_any(self, value: Any) -> bool:
        """Remove TTS keys recursively. Return True if changed."""
        changed = False

        if isinstance(value, dict):
            keys_to_delete = [k for k in value.keys() if k.lower() in self._scrub_keys]
            for k in keys_to_delete:
                del value[k]
                changed = True
            for k, v in list(value.items()):
                if self._scrub_any(v):
                    changed = True
            return changed

        if isinstance(value, list):
            for item in value:
                if self._scrub_any(item):
                    changed = True
            return changed

        return False

    def _scrub_jsonl_file(self, fpath: Path) -> bool:
        if not self.cfg.scrub_tts_fields:
            return False

        try:
            before = fpath.stat()
        except Exception:
            return False

        changed_any = False
        out_lines: list[str] = []

        try:
            with fpath.open("r", encoding="utf-8") as f:
                for line in f:
                    raw_line = line
                    newline = "\n"
                    if raw_line.endswith("\r\n"):
                        newline = "\r\n"
                    elif raw_line.endswith("\n"):
                        newline = "\n"
                    else:
                        newline = ""
                    line = line.strip()
                    if not line:
                        out_lines.append(raw_line)
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        out_lines.append(raw_line)
                        continue

                    changed = self._scrub_any(obj)
                    if changed:
                        changed_any = True
                        out_lines.append(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + newline)
                    else:
                        out_lines.append(raw_line)
        except Exception:
            return False

        if not changed_any:
            return False

        try:
            after = fpath.stat()
            if (after.st_mtime_ns != before.st_mtime_ns) or (after.st_size != before.st_size):
                return False
        except Exception:
            return False

        tmp_path = fpath.with_suffix(fpath.suffix + ".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                f.writelines(out_lines)
            # Re-verifie juste avant le replace pour eviter d'ecraser de nouvelles lignes.
            latest = fpath.stat()
            if (latest.st_mtime_ns != before.st_mtime_ns) or (latest.st_size != before.st_size):
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
                return False
            tmp_path.replace(fpath)
        except Exception:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
            return False

        return True

    def _maybe_scrub_file(self, fpath: Path):
        if not self.cfg.scrub_tts_fields:
            return

        now = time.time()
        if (now - self._last_scrub_time) < self.cfg.scrub_min_interval:
            return

        try:
            st = fpath.stat()
        except Exception:
            return

        if (now - st.st_mtime) < self.cfg.scrub_idle_seconds:
            return

        if self._scrub_jsonl_file(fpath):
            self._last_scrub_time = now
            try:
                self._pos = fpath.stat().st_size
            except Exception:
                self._pos = 0
            self._scrub_pending = False

    # -------- behavior --------

    def _emit(self, text: str):
        if not self.on_new_message:
            return
        try:
            self.on_new_message(text, "codex_sessions")
        except TypeError:
            # compat si callback ne prend qu'un arg
            self.on_new_message(text)

    def _prime_last_message(self, fpath: Path):
        """Lit tout le fichier et n'émet QUE la dernière réponse assistant."""
        if not self.cfg.read_last_on_start:
            return

        last_text: Optional[str] = None
        last_key: Optional[str] = None

        try:
            with fpath.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    res = self._extract_assistant_text(obj)
                    if res:
                        last_text, last_key = res
        except Exception:
            return

        if last_text and last_key and last_key != self._last_emitted_key:
            self._last_emitted_key = last_key
            self._emit(last_text)

    def _run(self):
        while not self._stop.is_set():
            latest = self._find_latest_rollout()

            # nouveau fichier (nouvelle session ou activity)
            if latest and latest != self._current_file:
                self._current_file = latest
                self.log(f"[sessions] Fichier suivi: {latest}")

                # 1) émettre uniquement la dernière réponse assistant existante
                self._prime_last_message(latest)
                if self.cfg.scrub_tts_fields:
                    self._scrub_pending = True
                    self._maybe_scrub_file(latest)

                # 2) puis se placer en fin
                try:
                    self._pos = latest.stat().st_size
                except Exception:
                    self._pos = 0

            if not self._current_file:
                time.sleep(self.cfg.poll_interval)
                continue

            try:
                with self._current_file.open("r", encoding="utf-8") as f:
                    f.seek(self._pos)
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue

                        res = self._extract_assistant_text(obj)
                        if res:
                            text, key = res
                            if key != self._last_emitted_key:
                                self._last_emitted_key = key
                                self._emit(text)

                        if self.cfg.scrub_tts_fields and self._scrub_any(obj):
                            self._scrub_pending = True

                    self._pos = f.tell()

            except Exception:
                # fichier en cours d'écriture/rotation
                pass

            if self._current_file and self._scrub_pending:
                self._maybe_scrub_file(self._current_file)

            time.sleep(self.cfg.poll_interval)
