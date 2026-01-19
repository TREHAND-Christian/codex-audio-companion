from pathlib import Path
import html
import re
import textwrap

try:
    import markdown as md
except Exception:
    md = None
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, TextLexer, guess_lexer
    from pygments.formatters import HtmlFormatter
except Exception:
    highlight = None

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextBrowser

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except Exception:
    QWebEngineView = None

from .ui_utils import apply_topmost, raise_chain

class TranslationWindow(QWidget):
    closed = Signal()
    positionChanged = Signal(int, int)
    sizeChanged = Signal(int, int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Traduction")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WA_QuitOnClose, False)
        self.setMinimumSize(420, 240)
        self.setStyleSheet("background-color: #1e1e1e;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._chat_css = self._load_chat_css()

        if QWebEngineView is not None:
            self.txt = QWebEngineView()
            self.txt.setContextMenuPolicy(Qt.NoContextMenu)
        else:
            self.txt = QTextBrowser()
            self.txt.setReadOnly(True)
            self.txt.setAcceptRichText(True)
            self.txt.setOpenExternalLinks(True)
            self.txt.setStyleSheet(
                "background-color: #1e1e1e; color: #d4d4d4; border: none;"
            )
        layout.addWidget(self.txt)

    def set_translation(self, text: str, label: str):
        if label:
            self.setWindowTitle(f"Traduction - {label}")
        else:
            self.setWindowTitle("Traduction")
        html_body = self._to_html(text or "")
        html_body = self._wrap_code_blocks(html_body)
        html_body = self._normalize_bullets(html_body)
        html_body = self._decorate_file_links(html_body)
        html_body = self._decorate_links(html_body)
        html_doc = self._wrap_html(html_body)
        if QWebEngineView is not None and isinstance(self.txt, QWebEngineView):
            self.txt.setHtml(html_doc)
        else:
            self.txt.setHtml(html_doc)

    def _load_chat_css(self) -> str:
        path = Path(__file__).with_name("translation_chat.css")
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""

    def _wrap_html(self, html_fragment: str) -> str:
        css = self._chat_css or ""
        return (
            "<!doctype html>"
            "<html><head><meta charset=\"utf-8\">"
            f"<style>{css}</style>"
            "</head><body class=\"chat-body\">"
            "<div class=\"chat-root\">"
            "<div class=\"chat-message\">"
            f"{html_fragment}"
            "</div></div></body></html>"
        )

    def _to_html(self, text: str) -> str:
        if not text:
            return ""
        if md is None:
            return self._simple_markdown_to_html(text)
        return md.markdown(
            text,
            extensions=[
                "fenced_code",
                "tables",
                "sane_lists",
                "nl2br",
            ],
            output_format="html5",
        )

    def _simple_markdown_to_html(self, text: str) -> str:
        lines = text.splitlines()
        html_lines = []
        in_code = False
        in_ul = False
        in_ol = False

        def close_lists():
            nonlocal in_ul, in_ol
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False

        for raw in lines:
            line = raw.rstrip("\r\n")
            if line.strip().startswith("```"):
                close_lists()
                if in_code:
                    html_lines.append("</code></pre>")
                    in_code = False
                else:
                    html_lines.append("<pre><code>")
                    in_code = True
                continue

            if in_code:
                html_lines.append(html.escape(line) + "\n")
                continue

            if not line.strip():
                close_lists()
                continue

            m_ul = re.match(r"^\s*([-*•]|[–—])\s+(.*)$", line)
            m_ol = re.match(r"^\s*\d+\.\s+(.*)$", line)
            if m_ul:
                if in_ol:
                    html_lines.append("</ol>")
                    in_ol = False
                if not in_ul:
                    html_lines.append("<ul>")
                    in_ul = True
                html_lines.append(f"<li>{self._inline_code(m_ul.group(2))}</li>")
                continue
            if m_ol:
                if in_ul:
                    html_lines.append("</ul>")
                    in_ul = False
                if not in_ol:
                    html_lines.append("<ol>")
                    in_ol = True
                html_lines.append(f"<li>{self._inline_code(m_ol.group(1))}</li>")
                continue

            close_lists()
            html_lines.append(f"<p>{self._inline_code(line)}</p>")

        if in_code:
            html_lines.append("</code></pre>")
        close_lists()
        return "\n".join(html_lines)

    def _inline_code(self, text: str) -> str:
        def repl(m):
            return f"<code>{html.escape(m.group(1))}</code>"

        escaped = html.escape(text)
        return re.sub(r"`([^`]+)`", repl, escaped)

    def _normalize_bullets(self, html_text: str) -> str:
        if not html_text:
            return ""

        pre_blocks = {}

        def stash_pre(m):
            key = f"__PRE_BLOCK_{len(pre_blocks)}__"
            pre_blocks[key] = m.group(0)
            return key

        tmp = re.sub(r"(?s)<pre><code>.*?</code></pre>", stash_pre, html_text)
        tmp = re.sub(r"(?s)<code class=\"whitespace-pre!\">.*?</code>", stash_pre, tmp)

        def split_paragraphs(html_chunk: str) -> str:
            out_lines = []
            para_re = re.compile(r"(?s)<p>(.*?)</p>")
            last = 0
            for m in para_re.finditer(html_chunk):
                out_lines.append(html_chunk[last:m.start()])
                out_lines.append(self._normalize_paragraph_bullets(m.group(1)))
                last = m.end()
            out_lines.append(html_chunk[last:])
            return "".join(out_lines)

        result = split_paragraphs(tmp)

        for key, block in pre_blocks.items():
            result = result.replace(key, block)
        return result

    def _normalize_paragraph_bullets(self, paragraph_html: str) -> str:
        parts = re.split(r"<br\s*/?>", paragraph_html)
        out = []
        in_ul = False
        bullet_re = re.compile(r"^\s*([-*•–—])\s+(.*)$")

        def close_ul():
            nonlocal in_ul
            if in_ul:
                out.append("</ul>")
                in_ul = False

        for part in parts:
            content = part.strip()
            if not content:
                close_ul()
                continue
            m = bullet_re.match(content)
            if m:
                if not in_ul:
                    out.append("<ul class=\"chat-ul\">")
                    in_ul = True
                out.append(f"<li>{m.group(2)}</li>")
            else:
                close_ul()
                out.append(f"<p>{content}</p>")

        close_ul()
        return "".join(out)


    def _wrap_code_blocks(self, html_text: str) -> str:
        if not html_text:
            return ""

        def repl(m):
            class_attr = m.group(1) or ""
            code_html = m.group(2) or ""

            # 1) Lang déclaré dans ```lang ?
            lang = None
            if class_attr:
                m_lang = re.search(r"(language|lang)-([a-z0-9_+-]+)", class_attr, re.I)
                if m_lang:
                    lang = m_lang.group(2).lower()

            # 2) Code brut + dé-indent propre
            raw_code = html.unescape(code_html).replace("\r\n", "\n")
            raw_code = textwrap.dedent(raw_code).strip("\n")
            detected_label = lang or "auto"
            rendered = html.escape(raw_code)

            # 3) Pygments (lang explicit sinon auto-detect)
            if highlight is not None:
                lexer = None

                if lang:
                    try:
                        lexer = get_lexer_by_name(lang, stripall=False)
                    except Exception:
                        lexer = None

                if lexer is None:
                    try:
                        lexer = guess_lexer(raw_code)
                        detected_label = (
                            lexer.aliases[0]
                            if getattr(lexer, "aliases", None)
                            else lexer.name
                        )
                    except Exception:
                        lexer = TextLexer(stripall=False)
                        detected_label = "text"

                formatter = HtmlFormatter(nowrap=True, noclasses=True, style="monokai")
                rendered = highlight(raw_code, lexer, formatter)

            safe_lang = html.escape(detected_label)

            return (
                '<div class="bg-token-text-code-block-background/10 border-token-input-background '
                'relative overflow-clip rounded-lg border contain-inline-size dark my-2">'
                '<div class="flex items-center text-token-description-foreground ps-2 pe-2 py-1 '
                'text-sm font-sans justify-between bg-token-side-bar-background select-none '
                'rounded-t-lg">'
                f'<div class="min-w-0 truncate">{safe_lang}</div>'
                '</div>'
                '<div class="text-size-code overflow-y-auto p-2" dir="ltr">'
                f'<code class="whitespace-pre!">{rendered}</code>'
                '</div></div>'
            )

        return re.sub(
            r"(?s)<pre><code(?: class=\"([^\"]+)\")?>(.*?)</code></pre>",
            repl,
            html_text,
        )

    def _decorate_file_links(self, html_text: str) -> str:


        if not html_text:
            return ""

        pre_blocks = {}

        def stash_pre(m):
            key = f"__PRE_BLOCK_{len(pre_blocks)}__"
            pre_blocks[key] = m.group(0)
            return key

        tmp = re.sub(r"(?s)<pre><code>.*?</code></pre>", stash_pre, html_text)
        tmp = re.sub(r"(?s)<code class=\"whitespace-pre!\">.*?</code>", stash_pre, tmp)

        def replace_inline_code(m):
            content = html.unescape(m.group(1))
            if self._looks_like_path(content):
                display = self._path_display_name(content)
                href = self._path_to_href(content)
                safe_display = html.escape(display)
                safe_href = html.escape(href, quote=True)
                return (
                    f"<a class=\"chat-file-link\" href=\"{safe_href}\">"
                    f"<span class=\"chat-file-name\">{safe_display}</span>"
                    "</a>"
                )
            if self._looks_like_function_call(content):
                safe = html.escape(content)
                return f"<span class=\"chat-file-link\">{safe}</span>"
            if self._looks_like_inline_link(content):
                safe = html.escape(content)
                return f"<code>{safe}</code>"
            if self._looks_like_style_token(content):
                safe = html.escape(content)
                return f"<code>{safe}</code>"
            if self._looks_like_code_inline(content):
                rendered = html.escape(content)
                if highlight is not None:
                    try:
                        lexer = get_lexer_by_name("python", stripall=False)
                    except Exception:
                        lexer = TextLexer(stripall=False)
                    formatter = HtmlFormatter(nowrap=True, noclasses=True, style="monokai")
                    rendered = highlight(content, lexer, formatter)
                return f"<code class=\"chat-inline-code\">{rendered}</code>"
            return f"<code>{m.group(1)}</code>"

        tmp = re.sub(r"<code>([^<]+)</code>", replace_inline_code, tmp)

        for key, block in pre_blocks.items():
            tmp = tmp.replace(key, block)
        return tmp

    def _looks_like_inline_link(self, text: str) -> bool:
        stripped = text.strip()
        if stripped.startswith("<") and "class=" in stripped:
            return True
        return False

    def _looks_like_function_call(self, text: str) -> bool:
        stripped = text.strip()
        return re.match(r"^[A-Z][A-Za-z0-9_]*\([^)]*\)$", stripped) is not None

    def _looks_like_style_token(self, text: str) -> bool:
        stripped = text.strip()
        if stripped.startswith("bg-token-") and "/10" in stripped:
            return True
        if stripped.startswith("text-token-"):
            return True
        if stripped.startswith("border-token-"):
            return True
        return False

    def _looks_like_code_inline(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        if re.search(r"[()=:{},;]", stripped):
            return True
        if re.search(r"\b(def|class|return|for|if|else|elif|try|except|import|from)\b", stripped):
            return True
        return False


    def _decorate_links(self, html_text: str) -> str:
        if not html_text:
            return ""

        blocks = {}

        def stash_block(m):
            key = f"__BLOCK_{len(blocks)}__"
            blocks[key] = m.group(0)
            return key

        tmp = re.sub(r"(?s)<pre>.*?</pre>", stash_block, html_text)
        tmp = re.sub(r"(?s)<code>.*?</code>", stash_block, tmp)

        parts = re.split(r"(<[^>]+>)", tmp)
        out = []
        in_anchor = False

        url_re = re.compile(r"(https?://[^\s<]+)", re.I)
        email_re = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")

        def repl_url(m):
            url = m.group(1)
            return f"<a class=\"chat-link\" href=\"{url}\">{url}</a>"

        def repl_email(m):
            email = m.group(1)
            return f"<a class=\"chat-link\" href=\"mailto:{email}\">{email}</a>"

        for part in parts:
            if not part:
                continue
            if part.startswith("<"):
                tag = part.lower()
                if tag.startswith("<a "):
                    in_anchor = True
                elif tag.startswith("</a"):
                    in_anchor = False
                out.append(part)
                continue

            if in_anchor:
                out.append(part)
                continue

            text = part
            text = url_re.sub(repl_url, text)
            text = email_re.sub(repl_email, text)
            out.append(text)

        result = "".join(out)
        for key, block in blocks.items():
            result = result.replace(key, block)
        return result

    def _path_to_href(self, text: str) -> str:
        try:
            p = Path(text).expanduser()
            if not p.is_absolute():
                p = (Path.cwd() / p).resolve()
            return p.as_uri()
        except Exception:
            return text

    def _path_display_name(self, text: str) -> str:
        try:
            return Path(text).name or text
        except Exception:
            return text

    def _looks_like_path(self, text: str) -> bool:
        if "<" in text or ">" in text:
            return False
        if text.lower().startswith("file://"):
            return False
        if text.startswith("bg-token-") and "/10" in text:
            return False
        if text.startswith("bg-") and re.search(r"/\d+$", text):
            return False
        if re.fullmatch(r"\\[0-9]+", text):
            return False
        if re.fullmatch(r"\\[nrtabfv]", text, flags=re.I):
            return False
        if text.startswith("\\") and text.count("\\") == 1:
            return False
        if "\\" in text:
            return True
        if "/" in text:
            # Avoid treating class-like tokens with a single slash as paths.
            if text.count("/") == 1 and "." not in text and not text.startswith("./") and not text.startswith("../"):
                return False
            return True
        if text.startswith("./") or text.startswith("../"):
            return True
        if re.match(r"^[A-Za-z]:\\\\", text):
            return True
        ext_match = re.search(
            r"\.([A-Za-z0-9]+)$",
            text,
        )
        if not ext_match:
            return False
        ext = ext_match.group(1).lower()
        return ext in {
            "py",
            "txt",
            "md",
            "json",
            "yaml",
            "yml",
            "ini",
            "toml",
            "css",
            "js",
            "ts",
            "tsx",
            "jsx",
            "rs",
            "go",
            "java",
            "cs",
            "cpp",
            "h",
            "hpp",
        }

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def moveEvent(self, event):
        self.positionChanged.emit(self.x(), self.y())
        super().moveEvent(event)

    def resizeEvent(self, event):
        self.sizeChanged.emit(self.width(), self.height())
        super().resizeEvent(event)
