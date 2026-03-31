# `audia.config` — Settings

All configuration is managed by the `Settings` class, which reads from environment variables
and `.env` files using [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

Use `get_settings()` to obtain the singleton instance:

```python
from audia.config import get_settings

cfg = get_settings()
print(cfg.llm_provider)   # "openai"
print(cfg.tts_backend)    # "edge-tts"
```

---

```{eval-rst}
.. automodule:: audia.config
   :members:
   :undoc-members:
   :show-inheritance:
```
