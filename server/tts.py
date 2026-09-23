from __future__ import annotations

import base64

from openai import OpenAI


def synthesize_speech(
    client: OpenAI,
    text: str,
    model: str,
    voice: str,
) -> str:
    """Return base64-encoded MP3, or empty string if synthesis fails."""
    if not text.strip():
        return ""
    try:
        response = client.audio.speech.create(
            model=model,
            voice=voice,
            input=text,
            response_format="mp3",
        )
        audio_bytes = response.content
        return base64.b64encode(audio_bytes).decode("ascii")
    except Exception:
        return ""
