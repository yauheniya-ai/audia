# LLM Backends

audia requires an LLM for the curation step. Two providers are supported.

---

## OpenAI

```dotenv
AUDIA_LLM_PROVIDER=openai
AUDIA_OPENAI_API_KEY=sk-...
AUDIA_LLM_MODEL=gpt-4o-mini       # default
```

Recommended models:

| Model | Notes |
|---|---|
| `gpt-4o-mini` | Default — fast, cheap, good quality |
| `gpt-4o` | Higher quality, higher cost |

### Custom endpoint

For Azure OpenAI, corporate proxies, or any OpenAI-compatible API:

```dotenv
AUDIA_OPENAI_API_BASE=https://your-org.openai.azure.com/
```

When set, all OpenAI calls (LLM curation **and** OpenAI TTS) are routed through this URL.

---

## Anthropic

```dotenv
AUDIA_LLM_PROVIDER=anthropic
AUDIA_ANTHROPIC_API_KEY=sk-ant-...
AUDIA_LLM_MODEL=claude-3-5-haiku-20241022
```

Recommended models:

| Model | Notes |
|---|---|
| `claude-3-5-haiku-20241022` | Fast and cost-effective |
| `claude-3-5-sonnet-20241022` | Higher quality |

### Custom endpoint

```dotenv
AUDIA_ANTHROPIC_API_BASE=https://your-proxy.example.com/
```

---

## Shared settings

| Variable | Default | Description |
|---|---|---|
| `AUDIA_LLM_MAX_CHUNK_CHARS` | `8000` | Characters per curation chunk |
| `AUDIA_LLM_TEMPERATURE` | `0.1` | 0 = deterministic, 1 = creative |

```{admonition} Temperature recommendation
:class: tip

Keep `AUDIA_LLM_TEMPERATURE` low (0.0 – 0.2) for curation tasks.
Higher values can introduce hallucinations into the audio script.
```

---

## How the LLM is used

The LLM receives each chunk with a system prompt instructing it to:

1. Rewrite all mathematical expressions in plain English
2. Replace tables with concise narrative sentences
3. Condense acknowledgements to a single sentence
4. Remove citation markers and reference lists entirely
5. Maintain a natural, engaging tone suitable for listening

For multi-chunk documents, each chunk after the first also receives the
**tail of the previous curated output** as context, ensuring smooth spoken
transitions across chunk boundaries.
