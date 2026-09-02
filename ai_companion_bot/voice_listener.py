import numpy as np
from faster_whisper import WhisperModel

# Load whisper model once at startup
# "small" is a good balance of speed and accuracy for most specs
print("[Whisper] Loading model...")
whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
print("[Whisper] Model loaded.")

SAMPLE_RATE = 48000   # Discord's native sample rate
CHANNELS = 2          # Discord sends stereo
SILENCE_THRESHOLD = 500    # amplitude below this = silence
SILENCE_DURATION = 1.5     # seconds of silence before we consider speech done
MIN_SPEECH_DURATION = 0.5  # minimum seconds of speech to bother transcribing

class VoiceListener:
    def __init__(self):
        self.audio_buffer = []
        self.silence_counter = 0
        self.is_speaking = False
        self.frames_per_second = SAMPLE_RATE // 20  # discord sends 20ms chunks

    def process_audio(self, data: bytes) -> str | None:
        """
        Process a chunk of raw PCM audio from Discord.
        Returns transcribed text when speech ends, None otherwise.
        """
        # Convert bytes to numpy array (Discord sends 16-bit PCM)
        audio_chunk = np.frombuffer(data, dtype=np.int16)

        # Convert stereo to mono
        if CHANNELS == 2:
            audio_chunk = audio_chunk.reshape(-1, 2).mean(axis=1).astype(np.int16)

        amplitude = np.abs(audio_chunk).mean()

        if amplitude > SILENCE_THRESHOLD:
            # Speech detected
            self.is_speaking = True
            self.silence_counter = 0
            self.audio_buffer.append(audio_chunk)
        elif self.is_speaking:
            # Silence after speech
            self.silence_counter += 1
            self.audio_buffer.append(audio_chunk)

            silence_seconds = self.silence_counter / (1000 / 20)  # 20ms chunks
            if silence_seconds >= SILENCE_DURATION:
                # Speech has ended — transcribe
                return self._transcribe()

        return None

    def _transcribe(self) -> str | None:
        """Transcribe buffered audio using faster-whisper."""
        if not self.audio_buffer:
            self._reset()
            return None

        # Combine all chunks
        audio_data = np.concatenate(self.audio_buffer)

        # Check minimum duration
        duration = len(audio_data) / SAMPLE_RATE
        if duration < MIN_SPEECH_DURATION:
            self._reset()
            return None

        # Convert to float32 for whisper
        audio_float = audio_data.astype(np.float32) / 32768.0

        try:
            segments, _ = whisper_model.transcribe(
                audio_float,
                language="en",
                beam_size=3,
                vad_filter=True  # built-in silence filtering
            )
            text = " ".join(seg.text for seg in segments).strip()
            print(f"[Whisper] Transcribed: {text}")
        except Exception as e:
            print(f"[Whisper] Transcription error: {e}")
            text = None

        self._reset()
        return text if text else None

    def _reset(self):
        """Reset buffer after transcription."""
        self.audio_buffer = []
        self.silence_counter = 0
        self.is_speaking = False
