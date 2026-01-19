from dataclasses import dataclass
import re


@dataclass
class TTSResult:
    display_text: str
    spoken_text: str
    effective_lang: str
    voice_id: str


class TTSPipeline:
    def __init__(self, tts_manager, translator=None):
        self.tts_manager = tts_manager
        self.translator = translator

    def process(self, text: str, target_lang: str, translate_enabled: bool,
                detected_lang: str = "", voice_id: str = "") -> TTSResult:
        effective_lang = self._resolve_effective_lang(target_lang, translate_enabled, detected_lang)
        display_text = self._translate_text(text, target_lang, translate_enabled)
        spoken_text = self._normalize_tts_text(self._strip_code(display_text))
        chosen_voice = voice_id
        if not chosen_voice or not self._voice_matches_lang(chosen_voice, effective_lang):
            chosen_voice = self._pick_voice_for_lang(effective_lang)
        return TTSResult(
            display_text=display_text,
            spoken_text=spoken_text,
            effective_lang=effective_lang,
            voice_id=chosen_voice,
        )

    def _resolve_effective_lang(self, target_lang: str, translate_enabled: bool, detected_lang: str) -> str:
        if translate_enabled:
            return (target_lang or "fr").lower()
        detected = (detected_lang or "").lower()
        if detected and detected != "?":
            return detected
        return (target_lang or "fr").lower()

    def _translate_text(self, text: str, target_lang: str, translate_enabled: bool) -> str:
        if not translate_enabled:
            return text
        if not self.translator:
            return text
        masked, mapping = self._mask_code(text)
        try:
            tr = self.translator.translate(masked, dest=target_lang)
            translated = tr.text or masked
            return self._unmask_code(translated, mapping)
        except Exception:
            return text

    def _normalize_tts_text(self, text: str) -> str:
        if not text:
            return text

        text = re.sub(r"\*{2,}", " astérisque ", text)
        text = text.replace("*", " astérisque ")
        text = re.sub(r"(astérisque\s+){2,}", "astérisque ", text, flags=re.I)

        def replace_specials(token: str) -> str:
            return (
                token.replace("\\", " barre oblique inverse ")
                .replace("/", " barre oblique ")
                .replace("_", " underscore ")
                .replace("-", " tiret ")
                .replace(".", " point ")
            )

        text = re.sub(
            r"([A-Za-z0-9][A-Za-z0-9._-]*[\\/][A-Za-z0-9._\\\\/\\-]+)",
            lambda m: replace_specials(m.group(1)),
            text,
        )

        text = re.sub(
            r"\b([A-Za-z0-9][A-Za-z0-9._-]*\.[A-Za-z0-9][A-Za-z0-9._-]*)\b",
            lambda m: replace_specials(m.group(1)),
            text,
        )

        return text

    def _mask_code(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        mapping: list[tuple[str, str]] = []

        def mask(pattern: str, src: str, prefix: str) -> str:
            idx = 0

            def repl(m):
                nonlocal idx
                token = f"<<<{prefix}{idx}>>>"
                mapping.append((token, m.group(0)))
                idx += 1
                return token

            return re.sub(pattern, repl, src, flags=re.S)

        masked = mask(r"```.*?```", text, "CODEBLOCK")
        masked = mask(r"`[^`\n]+`", masked, "INLINE")
        return masked, mapping

    def _unmask_code(self, text: str, mapping: list[tuple[str, str]]) -> str:
        out = text
        for token, original in mapping:
            out = out.replace(token, original)
        return out

    def _strip_code(self, text: str) -> str:
        if not text:
            return text
        out = re.sub(r"```.*?```", " ", text, flags=re.S)
        out = re.sub(r"`([^`\n]+)`", r"\1", out)
        out = re.sub(r"\s{2,}", " ", out)
        return out.strip()

    def _pick_voice_for_lang(self, lang: str) -> str:
        if hasattr(self.tts_manager, "pick_voice_for_lang"):
            return self.tts_manager.pick_voice_for_lang(lang)
        return ""

    def _voice_matches_lang(self, voice_id: str, lang: str) -> bool:
        lang = (lang or "").lower()
        if not voice_id:
            return False
        voices = self.tts_manager.list_voices() if hasattr(self.tts_manager, "list_voices") else []
        for v in voices:
            if v.get("id") != voice_id:
                continue
            langs = [str(x).lower() for x in (v.get("languages") or [])]
            return any(l.startswith(lang) for l in langs)
        return False
