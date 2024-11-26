import os
from datetime import datetime
from pathlib import Path
import subprocess
from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncio
from collections import deque
from threading import Lock
import uvicorn
import openai
openai.api_key =  os.getenv("OPENAI_API_KEY")
# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up templates directory
templates = Jinja2Templates(directory="templates")

# Ensure directories exist
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)

templates_dir = Path("templates")
templates_dir.mkdir(exist_ok=True)

# Create index.html in templates directory if missing
index_html = templates_dir / "index.html"
if not index_html.exists():
    with open(index_html, "w") as f:
        f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>Real-Time Whisper Out Transcription</title>
    <script src="/static/audio-capture.js"></script>
    <style>
        body { max-width: 800px; margin: 0 auto; padding: 20px; font-family: Arial, sans-serif; }
        .controls { display: flex; gap: 10px; margin: 20px 0; }
        button { padding: 10px 20px; cursor: pointer; }
        #transcription { width: 100%; height: 200px; margin-top: 20px; padding: 10px; }
    </style>
</head>
<body>
    <h1>🎙️ Real-Time Whisper Transcription</h1>
    <div class="controls">
        <button onclick="window.startRecording()">🔴 Start Recording</button>
        <button onclick="window.stopRecording()">⏹️ Stop Recording</button>
    </div>
    <textarea id="transcription" readonly placeholder="Transcription will appear here..."></textarea>
</body>
</html>
        """)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")


class AudioTranscriptionManager:
    def __init__(self):
        self.RATE = 16000
        self.CHANNELS = 1
        self.audio_chunks = deque()  # Thread-safe queue for audio chunks
        self.lock = Lock()  # Ensure thread safety during chunk processing
        self.output_dir = Path("audio_chunks")
        self.output_dir.mkdir(exist_ok=True)
        self.t_headers = None
        self.transcription = None

    def save_raw_audio_to_file(self, raw_audio_data, filename):
        # Save raw audio data to a temporary file
        with open(filename, "wb") as f:
            f.write(raw_audio_data)
        print(f"Raw audio saved to {filename}")

    async def transcribe_audio(self, temp_audio_file):
        with open(temp_audio_file, 'rb') as audio_file:
            print("Attempting transcription...")
            try:
                transcription = openai.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-1",
                    language="ro",
                    response_format="text"
                )
            except Exception as e:
                print(f"Transcription error: {e}")
                transcription = None
        print(f"Transcription: {transcription}")
        return transcription.strip() if transcription else None

                            


    async def convert_audio_to_wav(self, raw_file, wav_file):
        # Convert raw audio (e.g., webm/opus) to WAV using ffmpeg
        try:
            subprocess.run([
                "ffmpeg", "-y",
                "-i", raw_file,         # Input raw audio file
                "-ar", "16000",         # Set sample rate
                "-ac", "1",             # Mono audio
                wav_file                # Output WAV file
            ], check=True)
            print(f"Converted {raw_file} to {wav_file}")
        except subprocess.CalledProcessError as e:
            print(f"Error converting audio: {e.stderr}")

    async def process_audio_chunks(self):
        while True:
            with self.lock:
                if len(self.audio_chunks) > 8:
                    print(f"Processing {len(self.audio_chunks)} audio chunks... at {datetime.now()}")
                    # Keep the first chunk and process the next 5 chunks
                    if not self.t_headers:
                        header_chunk = self.audio_chunks[0]
                        self.t_headers = header_chunk
                    chunks_to_process = [
                        self.audio_chunks.popleft()
                        for _ in range(min(9, len(self.audio_chunks)))
                    ]
                    # Re-add the header chunk to the front
                    self.audio_chunks.appendleft(self.t_headers)
                else:
                    chunks_to_process = []

            if chunks_to_process:
                combined_audio = b''.join(chunks_to_process)

                # Generate temporary raw audio and final WAV file paths
                raw_audio_file = self.output_dir / f"chunk_{datetime.now().strftime('%Y%m%d_%H%M%S')}.webm"
                wav_audio_file = self.output_dir / f"chunk_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"

                # Save raw audio
                self.save_raw_audio_to_file(combined_audio, raw_audio_file)

                # Convert raw audio to WAV format
                await self.convert_audio_to_wav(raw_audio_file, wav_audio_file)

                # Cleanup raw audio file
                if raw_audio_file.exists():
                    os.remove(raw_audio_file)
                    print(f"Deleted temporary raw audio file: {raw_audio_file}")

                # Transcribe the WAV audio
                transcription = await self.transcribe_audio(wav_audio_file)
                if transcription:
                    self.transcription = transcription
                print(f"Final WAV saved to {wav_audio_file}")

            await asyncio.sleep(0.1)  # Allow other tasks to run

    def add_audio_data(self, audio_data):
        with self.lock:
            self.audio_chunks.append(audio_data)

    def clear_transcription(self):
        self.transcription = None



@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket connection established")

    audio_manager = AudioTranscriptionManager()

    # Start a background task to process audio chunks
    processing_task = asyncio.create_task(audio_manager.process_audio_chunks())

    try:
        while True:
            # Receive audio data from client
            audio_data = await websocket.receive_bytes()
            print(f"Received audio chunk of size {len(audio_data)} bytes")

            # Add audio data to the manager for processing
            audio_manager.add_audio_data(audio_data)

            if audio_manager.transcription:  
                try:
                    await websocket.send_text(audio_manager.transcription)
                    audio_manager.clear_transcription()
                except Exception as e:
                    print(f"Failed to send transcription: {e}") 

    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        print("WebSocket connection closed")
        processing_task.cancel()
        await websocket.close()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
