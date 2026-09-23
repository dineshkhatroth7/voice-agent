const talkBtn = document.getElementById("talk");
const statusEl = document.getElementById("status");
const orb = document.getElementById("orb");
const log = document.getElementById("log");
const canvas = document.getElementById("wave");
const ctx = canvas.getContext("2d");

let mediaStream = null;
let mediaRecorder = null;
let chunks = [];
let analyser = null;
let audioCtx = null;
let raf = 0;
let playback = null;

function setState(state, message) {
  orb.dataset.state = state;
  statusEl.textContent = message;
}

function addBubble(role, text) {
  const el = document.createElement("div");
  el.className = `bubble ${role}`;
  el.innerHTML = `<small>${role === "user" ? "You" : "Agent"}</small>${escapeHtml(text)}`;
  log.prepend(el);
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function drawWave() {
  const { width, height } = canvas;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#6ea8ff";
  if (!analyser) {
    ctx.fillRect(20, height / 2 - 2, width - 40, 4);
    return;
  }
  const data = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(data);
  const step = Math.max(1, Math.floor(data.length / 64));
  const barW = width / 64;
  for (let i = 0; i < 64; i += 1) {
    const v = Math.abs(data[i * step] - 128) / 128;
    const h = Math.max(4, v * height);
    ctx.fillRect(i * barW + 2, (height - h) / 2, barW - 4, h);
  }
  raf = requestAnimationFrame(drawWave);
}

async function ensureMic() {
  if (mediaStream) return mediaStream;
  mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioCtx = new AudioContext();
  const source = audioCtx.createMediaStreamSource(mediaStream);
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 2048;
  source.connect(analyser);
  return mediaStream;
}

function pickMime() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

async function startRecording() {
  if (playback) {
    playback.pause();
    playback = null;
  }
  const stream = await ensureMic();
  chunks = [];
  const mimeType = pickMime();
  mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size) chunks.push(event.data);
  };
  mediaRecorder.start();
  talkBtn.dataset.recording = "true";
  talkBtn.textContent = "Stop";
  setState("listening", "Listening… click Stop when you finish speaking");
  cancelAnimationFrame(raf);
  drawWave();
}

async function stopRecording() {
  if (!mediaRecorder || mediaRecorder.state === "inactive") return;
  const blob = await new Promise((resolve) => {
    mediaRecorder.onstop = () => {
      resolve(new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" }));
    };
    mediaRecorder.stop();
  });
  talkBtn.dataset.recording = "false";
  talkBtn.textContent = "Talk";
  talkBtn.disabled = true;
  setState("transcribing", "Transcribing your speech…");
  try {
    const form = new FormData();
    const ext = blob.type.includes("mp4") ? "mp4" : "webm";
    form.append("audio", blob, `turn.${ext}`);
    const response = await fetch("/api/turn", { method: "POST", body: form });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Turn failed");
    }
    if (payload.transcript) addBubble("user", payload.transcript);
    addBubble("agent", payload.reply);
    setState("speaking", "Speaking…");
    await speakReply(payload.reply, payload.audio_base64, payload.mime);
    setState("idle", "Idle — click Talk to go again");
  } catch (error) {
    setState("idle", error.message || "Something went wrong");
    addBubble("agent", error.message || "Something went wrong");
  } finally {
    talkBtn.disabled = false;
    cancelAnimationFrame(raf);
  }
}

function speakWithBrowser(text) {
  return new Promise((resolve) => {
    if (!window.speechSynthesis) {
      resolve();
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onend = resolve;
    utterance.onerror = resolve;
    speechSynthesis.speak(utterance);
  });
}

async function speakReply(text, audioBase64, mime) {
  if (audioBase64) {
    const bytes = Uint8Array.from(atob(audioBase64), (c) => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: mime || "audio/mpeg" }));
    playback = new Audio(url);
    await new Promise((resolve) => {
      playback.onended = resolve;
      playback.onerror = resolve;
      playback.play().catch(resolve);
    });
    URL.revokeObjectURL(url);
    return;
  }
  await speakWithBrowser(text);
}

talkBtn.addEventListener("click", async () => {
  try {
    if (talkBtn.dataset.recording === "true") {
      await stopRecording();
      return;
    }
    await startRecording();
  } catch (error) {
    setState("idle", error.message || "Microphone permission is required");
  }
});

drawWave();
