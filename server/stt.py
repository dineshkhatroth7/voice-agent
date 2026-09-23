from __future__ import annotations

import io
from openai import OpenAI


def transcribe_audio(
    client: OpenAI,
    data: bytes,
    filename: str,
    model: str,
) -> str:
    buffer = io.BytesIO(data)
    buffer.name = filename or "audio.webm"
    transcript = client.audio.transcriptions.create(
        model=model,
        file=buffer,
        response_format="text",
    )
    if isinstance(transcript, str):
        return transcript.strip()
    return str(transcript).strip()
