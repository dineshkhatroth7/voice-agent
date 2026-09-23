from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel

from server.agent import SessionMemory, chat_reply
from server.stt import transcribe_audio
from server.tts import synthesize_speech

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

WEB = ROOT / "web"
memory = SessionMemory()
app = FastAPI(title="Voice Agent POC")


def openai_client() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is missing. Copy .env.example to .env and add your key.",
        )
    return OpenAI(api_key=key)


class ChatBody(BaseModel):
    text: str


class SpeakBody(BaseModel):
    text: str


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "has_openai_key": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "notes": len(memory.notes),
        "devices": memory.devices,
    }


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict:
    client = openai_client()
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    text = transcribe_audio(
        client,
        data,
        audio.filename or "audio.webm",
        os.getenv("OPENAI_STT_MODEL", "whisper-1"),
    )
    return {"transcript": text}


@app.post("/api/chat")
def chat(body: ChatBody) -> dict:
    client = openai_client()
    reply = chat_reply(
        client,
        os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        body.text,
        memory,
    )
    return {"reply": reply}


@app.post("/api/speak")
def speak(body: SpeakBody) -> dict:
    client = openai_client()
    audio_b64 = synthesize_speech(
        client,
        body.text,
        os.getenv("OPENAI_TTS_MODEL", "tts-1"),
        os.getenv("OPENAI_TTS_VOICE", "alloy"),
    )
    return {"audio_base64": audio_b64, "mime": "audio/mpeg"}


@app.post("/api/turn")
async def turn(audio: UploadFile | None = File(None), text: str = Form("")) -> dict:
    client = openai_client()
    transcript = text.strip()
    if not transcript:
        if audio is None:
            raise HTTPException(status_code=400, detail="Provide audio or text")
        data = await audio.read()
        if not data:
            raise HTTPException(status_code=400, detail="Provide audio or text")
        transcript = transcribe_audio(
            client,
            data,
            audio.filename or "audio.webm",
            os.getenv("OPENAI_STT_MODEL", "whisper-1"),
        )
    if not transcript:
        return {
            "transcript": "",
            "reply": "I didn't hear anything. Try talking a bit closer to the mic.",
            "audio_base64": "",
            "mime": "audio/mpeg",
        }

    reply = chat_reply(
        client,
        os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        transcript,
        memory,
    )
    audio_b64 = synthesize_speech(
        client,
        reply,
        os.getenv("OPENAI_TTS_MODEL", "tts-1"),
        os.getenv("OPENAI_TTS_VOICE", "alloy"),
    )
    return {
        "transcript": transcript,
        "reply": reply,
        "audio_base64": audio_b64,
        "mime": "audio/mpeg",
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
