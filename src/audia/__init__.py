"""
audia – Turn documents into audio, intelligently.

Core pipeline: PDF → text extraction → agentic cleaning → TTS → audio file.
Optional: ArXiv research → select paper → pipeline above.
"""

from importlib.metadata import version

__version__ = version("audia")
__author__ = "Yauheniya Varabyova"

from audia.config import Settings, get_settings  # noqa: F401

__all__ = ["Settings", "get_settings", "__version__"]
