# Voice Agent POC

Browser microphone → Whisper STT → LLM + tools → TTS. First slice of a voice / video / physical AI agent loop: **sense → reason → act**.

## Run

```powershell
cd $env:USERPROFILE\voice-agent-poc
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Put your OpenAI key in `.env`, then:

```powershell
.\.venv\Scripts\python -m uvicorn server.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 → allow the mic → **Talk** → **Stop**.

Chrome or Edge is recommended. `OPENAI_API_KEY` is required for transcription and chat. If TTS fails, the page falls back to `speechSynthesis`.

## Tools in this demo

- Current time
- Session notes (`remember` / `what did I tell you`)
- Calculator and a few unit conversions
- Placeholder devices (`turn on the lights`) for a later physical-AI mapping

## Next

| Agent | Now | Later |
| --- | --- | --- |
| Voice | Turn-based STT/LLM/TTS | Barge-in, OpenAI Realtime |
| Video | Same agent | Camera frames / avatar |
| Physical | `set_device` stub | MQTT / ROS / robot SDK |
