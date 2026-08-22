"""Renders visual slides (title card, code card, complexity card) as PNG
images using an HTML/CSS template + Playwright screenshot. Themed via
variation_engine so the visual style rotates automatically week to week
instead of looking identical on every upload.
"""

import os
import sys

from jinja2 import Template
from playwright.sync_api import sync_playwright
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

# On Windows, background threads (e.g. FastAPI's BackgroundTasks) default to
# SelectorEventLoop, which cannot spawn subprocesses -- and Playwright launches
# Chromium as a subprocess internally. Forcing ProactorEventLoopPolicy here
# (process-wide, safe to set once) fixes "NotImplementedError" on that path.
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 720p instead of 1080p -- meaningfully reduces memory usage during video
# encoding, which matters on memory-constrained hosts (e.g. Render's free
# tier at 512MB RAM). Still looks sharp on YouTube; upgrade if you move to a
# host/plan with more RAM.
SLIDE_WIDTH = 1280
SLIDE_HEIGHT = 720

# Base template now takes bg/text/accent/font as theme variables instead of
# hardcoded colors -- variation_engine.get_weekly_theme() supplies these.
BASE_TEMPLATE = Template("""
<html>
<head>
<style>
  body {
    margin: 0;
    width: {{ width }}px;
    height: {{ height }}px;
    background: {{ theme.bg }};
    color: {{ theme.text }};
    font-family: {{ theme.font }};
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 80px;
    box-sizing: border-box;
  }
  h1 { font-size: 64px; margin-bottom: 20px; color: {{ theme.accent }}; }
  h2 { font-size: 40px; margin-bottom: 30px; color: {{ theme.text }}; opacity: 0.65; font-weight: normal; }
  .badge {
    display: inline-block;
    padding: 8px 24px;
    border-radius: 20px;
    font-size: 28px;
    font-weight: bold;
    margin-bottom: 30px;
  }
  .easy { background: #1a7f37; }
  .medium { background: #9a6700; }
  .hard { background: #a40e26; }
  .complexity-box {
    display: flex;
    gap: 60px;
    margin-top: 40px;
  }
  .complexity-item {
    font-size: 36px;
    background: rgba(255,255,255,0.06);
    padding: 30px 50px;
    border-radius: 12px;
    border: 2px solid {{ theme.accent }};
  }
  {{ pygments_css }}
  pre { font-size: 26px; line-height: 1.5; border-radius: 12px; padding: 40px; }
</style>
</head>
<body>
  {{ body|safe }}
</body>
</html>
""")


def _render_html_to_png(html: str, output_path: str, width: int = SLIDE_WIDTH, height: int = SLIDE_HEIGHT) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html)
        page.screenshot(path=output_path)
        browser.close()
    return output_path


def render_title_slide(title: str, difficulty: str, theme: dict, output_path: str) -> str:
    body = f"""
      <div class="badge {difficulty.lower()}">{difficulty}</div>
      <h1>{title}</h1>
      <h2>LeetCode Problem of the Day</h2>
    """
    html = BASE_TEMPLATE.render(width=SLIDE_WIDTH, height=SLIDE_HEIGHT, theme=theme, pygments_css="", body=body)
    return _render_html_to_png(html, output_path)


def render_code_slide(code: str, theme: dict, output_path: str) -> str:
    formatter = HtmlFormatter(style="monokai", noclasses=False)
    highlighted = highlight(code, PythonLexer(), formatter)
    pygments_css = formatter.get_style_defs(".highlight")
    body = f'<div class="highlight-wrapper">{highlighted}</div>'
    html = BASE_TEMPLATE.render(
        width=SLIDE_WIDTH, height=SLIDE_HEIGHT, theme=theme, pygments_css=pygments_css, body=body
    )
    return _render_html_to_png(html, output_path)


def render_complexity_slide(time_complexity: str, space_complexity: str, theme: dict, output_path: str) -> str:
    body = f"""
      <h1>Complexity Analysis</h1>
      <div class="complexity-box">
        <div class="complexity-item">⏱ Time: {time_complexity}</div>
        <div class="complexity-item">💾 Space: {space_complexity}</div>
      </div>
    """
    html = BASE_TEMPLATE.render(width=SLIDE_WIDTH, height=SLIDE_HEIGHT, theme=theme, pygments_css="", body=body)
    return _render_html_to_png(html, output_path)


def render_thumbnail(title: str, difficulty: str, theme: dict, output_path: str) -> str:
    """Renders a 1280x720 YouTube thumbnail -- big bold text, high contrast,
    designed to be legible even at small preview sizes. Without this, YouTube
    auto-grabs a random video frame as the thumbnail, which looks unprofessional."""
    # Truncate long titles so text doesn't overflow the thumbnail
    display_title = title if len(title) <= 40 else title[:37] + "..."
    body = f"""
      <div class="badge {difficulty.lower()}" style="font-size:32px;">{difficulty}</div>
      <h1 style="font-size:96px; line-height:1.1;">{display_title}</h1>
      <h2 style="font-size:44px;">LeetCode Daily Challenge</h2>
    """
    html = BASE_TEMPLATE.render(width=1280, height=720, theme=theme, pygments_css="", body=body)
    return _render_html_to_png(html, output_path, width=1280, height=720)