# AI Companion — Discord Bot

An AI-driven Discord companion with a persistent personality, long-term
memory, text chat, and voice-channel conversation via speech-to-text + TTS.

## Architecture

```
main.py             Discord bot entrypoint: DM text chat, voice-channel
                     auto-join/leave, recording, and random self-initiated DMs.

methods.py           Builds the system prompt (persona + injected memory) and
                     talks to the local LLM (Ollama, model "companion") to
                     generate replies. Two modes: full response (text chat)
                     and sentence-by-sentence streaming (voice).

memory.py            SQLite-backed memory system:
                      - rolling short-term chat history per channel
                      - long-term "facts about the user" and
                        "facts about the bot" (auto-extracted via LLM,
                        deduplicated, auto-summarised when they grow too large)
                      - periodic conversation summaries so old context isn't
                        lost when history is compressed

manage_memory.py     Standalone CLI to inspect/edit the memory database
                     (view/add/delete facts, view history & summaries).

voice_listener.py    Buffers raw PCM audio from a Discord voice channel,
                     detects speech vs silence, and transcribes with
                     faster-whisper.

tts.py               Converts the bot's text replies to speech with edge-tts,
                     then reshapes the audio with an ffmpeg chain
                     (EQ, compression, reverb, pitch/tempo).

Modelfile            Ollama Modelfile defining the "companion" model: base
                     model, system prompt, and a few example exchanges.
                     Swap the SYSTEM prompt for any persona you like.
```

## How it works, end to end

1. The user DMs the bot, or joins a voice channel with it.
2. `main.py` hands the raw input to `methods.generate_response` (text) or
   records + transcribes voice via `voice_listener.py`, then does the same.
3. `methods.py` pulls recent history + long-term facts + summaries from
   `memory.py`, builds a system prompt, and calls the local LLM.
4. The reply is saved back into `memory.py`, and (for voice) converted to
   speech by `tts.py` and played into the voice channel.
5. Every 20 messages in a channel, `memory.py` runs background threads to
   extract new long-term facts and compress/summarise old history.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your bot token + your Discord user ID
ollama create companion -f Modelfile
python main.py
```

Requires a local [Ollama](https://ollama.com) install with the `companion`
model created from `Modelfile`, and `ffmpeg` on PATH for TTS post-processing.

## Note

This is the core Discord bot + AI agent (memory, reasoning, voice) from a
larger personal project — persona-specific content and personal identifiers
have been stripped out for demonstration purposes. Swap the `SYSTEM_PROMPT`
in `methods.py` and `Modelfile` for any personality you want.
