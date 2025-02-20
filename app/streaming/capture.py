import subprocess
import threading
import time
import uuid

try:
    import whisper
except ImportError:
    whisper = None

class StreamCapture:
    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self.id = str(uuid.uuid4())
        self.capture_file = f"{self.id}.mp4"
        self.transcript_file = f"{self.id}.txt"
        self.process = None
        self.capturing = False

    def start_capture(self) -> None:
        self.capturing = True
        command = ["ffmpeg", "-i", self.stream_url, "-c", "copy", self.capture_file]
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        threading.Thread(target=self.run_transcription, daemon=True).start()

    def stop_capture(self) -> None:
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.capturing = False

    def run_transcription(self) -> None:
        # Wait until capturing stops
        while self.capturing:
            time.sleep(5)
        transcript = ""
        if whisper:
            model = whisper.load_model("base")
            result = model.transcribe(self.capture_file)
            transcript = result.get("text", "")
        else:
            transcript = "Transcription not available. Install Whisper for transcription."
        with open(self.transcript_file, "w") as f:
            f.write(transcript)