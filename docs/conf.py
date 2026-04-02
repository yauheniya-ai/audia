# Configuration file for the Sphinx documentation builder.
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import sys
import os

# Make the audia package importable for autodoc
sys.path.insert(0, os.path.abspath("../src"))

# ── Project info ──────────────────────────────────────────────────────────────
project = "audia"
copyright = "2026, Yauheniya Varabyova"
author = "Yauheniya Varabyova"

try:
    from audia import __version__
    release = __version__
    version = ".".join(release.split(".")[:2])
except Exception:
    release = version = "latest"

# ── Extensions ────────────────────────────────────────────────────────────────
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_copybutton",
    "myst_parser",
]

autosummary_generate = True

napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_use_admonition_for_notes = True

autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_typehints = "description"
autodoc_mock_imports = [
    "langchain_openai",
    "langchain_anthropic",
    "langchain",
    "langchain_core",
    "langgraph",
    "faster_whisper",
    "sounddevice",
    "soundfile",
    "edge_tts",
    "kokoro",
    "fitz",
    "pymupdf",
    "arxiv",
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "openai",
    "anthropic",
    "typer",
    "rich",
    "aiofiles",
    "numpy",
]

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "html_admonition",
    "html_image",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://docs.pydantic.dev/latest", None),
}

# ── Source files ──────────────────────────────────────────────────────────────
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
master_doc = "index"

# ── Exclusions ────────────────────────────────────────────────────────────────
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# ── Theme ─────────────────────────────────────────────────────────────────────
html_theme = "sphinx_rtd_theme"
html_title = "audia"
html_short_title = "audia"
html_show_sourcelink = False
html_show_sphinx = False
html_copy_source = False

html_theme_options = {
    "logo_only": False,
    "version_selector": False,
    "prev_next_buttons_location": "bottom",
    "style_external_links": False,
    "collapse_navigation": False,
    "sticky_navigation": True,
    "navigation_depth": 4,
    "includehidden": True,
    "titles_only": False,
    "style_nav_header_background": "#0d0d14",
}

# Custom static files
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_js_files = ["theme_toggle.js"]

# Template overrides
templates_path = ["_templates"]

html_favicon = None

# Copybutton settings
copybutton_prompt_text = r"\$ |>>> |\.\.\. "
copybutton_prompt_is_regexp = True
