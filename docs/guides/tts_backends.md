# TTS Backends

audia supports three TTS backends, selectable via `AUDIA_TTS_BACKEND`.

---

## edge-tts (default)

Microsoft Edge's TTS service, accessed via the
[edge-tts](https://github.com/rany2/edge-tts) library.

- **No API key required**
- Requires internet access
- 400+ voices across many languages
- Default voice: `en-US-AriaNeural`

```dotenv
AUDIA_TTS_BACKEND=edge-tts
AUDIA_TTS_VOICE=en-US-AriaNeural
AUDIA_TTS_RATE=+0%
```

List all available voices:

```bash
edge-tts --list-voices
```

Popular English voices:

| Voice | Gender | Accent |
|---|---|---|
| `en-US-AriaNeural` | Female | US |
| `en-US-GuyNeural` | Male | US |
| `en-GB-SoniaNeural` | Female | British |
| `en-GB-RyanNeural` | Male | British |
| `en-AU-NatashaNeural` | Female | Australian |

---

## Kokoro (local)

[Kokoro](https://github.com/hexgrad/kokoro) is a local neural TTS model — no internet,
no API key, GPU optional.

```bash
pip install "audia[kokoro]"
```

```dotenv
AUDIA_TTS_BACKEND=kokoro
AUDIA_TTS_VOICE=af_heart
```

See the [Kokoro documentation](https://huggingface.co/hexgrad/Kokoro-82M) for the full voice list.

---

## OpenAI TTS

High-quality TTS via the OpenAI API. Requires an OpenAI API key and incurs cost.

```dotenv
AUDIA_TTS_BACKEND=openai
AUDIA_TTS_VOICE=nova
# AUDIA_OPENAI_API_KEY is required
```

Available voices: `alloy`, `echo`, `nova`, `shimmer`, `onyx`, `fable`

---

## Chunk size tuning

Long texts are split into chunks before synthesis. The default of 3800 characters works well
for edge-tts; OpenAI's hard limit is 4096 characters.

```dotenv
AUDIA_TTS_CHUNK_CHARS=3800
```

All chunks are synthesised independently and then concatenated into one final `.mp3`.
