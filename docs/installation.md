# Installation

## Requirements

- Python **3.10** or later
- A configured LLM provider (OpenAI or Anthropic) — required for the curation step

## Standard install

```bash
pip install audia
```

## Recommended: pipx

[pipx](https://pipx.pypa.io/) installs `audia` in an isolated environment and exposes the
`audia` command globally — no virtualenv management required.

```bash
pipx install audia
```

## Optional extras

| Extra | What it adds |
|---|---|
| `kokoro` | Local Kokoro TTS (no internet, GPU optional) |
| `docs` | Sphinx + extensions for building these docs |
| `dev` | Full dev toolchain (pytest, ruff, mypy, pre-commit, …) |

```bash
pip install "audia[kokoro]"
pip install "audia[dev]"
```

## Install from source

```bash
git clone https://github.com/yauheniya-ai/audia
cd audia/pypi
pip install -e ".[dev]"
```

## Verify

```bash
audia --version
audia info
```

`audia info` prints all active settings — useful to confirm your `.env` is loaded correctly.
