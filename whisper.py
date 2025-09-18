from faster_whisper import WhisperModel
import sounddevice as sd
import soundfile as sf
import io

# Record audio for 5 seconds
def record(seconds=5, sr=16000):
    print("Recording... speak now")
    audio = sd.rec(int(seconds*sr), samplerate=sr, channels=1, dtype="float32")
    sd.wait()
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV")
    return buf.getvalue()

def transcribe(wav_bytes):
    # Pick your model: "tiny", "base", "small", "medium", "large-v3"
    model = WhisperModel("small", device="cpu", compute_type="int8")
    with open("./recordings/temp.wav", "wb") as f:  # faster-whisper expects a file path
        f.write(wav_bytes)
    segments, info = model.transcribe("./recordings/temp.wav", vad_filter=True)
    text = " ".join(seg.text for seg in segments)
    return text, info.language

if __name__ == "__main__":
    wav = record(5)
    text, lang = transcribe(wav)
    print(f"Detected language: {lang}")
    print("Transcribed text:", text)
