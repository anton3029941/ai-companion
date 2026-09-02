import edge_tts
import asyncio
import subprocess
import os

VOICE = "en-US-AriaNeural"
RATE = "-10%"
PITCH = "+0Hz"
DEFAULT_OUTPUT = "tts_output.mp3"

def postprocess_audio(input_path: str, output_path: str) -> str:
    """Apply EQ, compression, reverb and tempo via ffmpeg."""
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-af", (
            # EQ: boost 150-300Hz +2dB, cut 3-5kHz -3dB, cut 8kHz+ -2dB
            "equalizer=f=220:width_type=o:width=2:g=2,"
            "equalizer=f=4000:width_type=o:width=2:g=-3,"
            "equalizer=f=10000:width_type=o:width=2:g=-2,"
            # Compression: threshold=-18dB, ratio=2:1
            "acompressor=threshold=-18dB:ratio=2:attack=20:release=200:makeup=6dB,"
            # Reverb: room size 10%, mix 6%
            "aecho=0.94:0.06:50:0.3,"
            # Tempo: -5% (atempo=0.95)
            "atempo=0.95,"
            "loudnorm=I=-16:TP=-1.5:LRA=11"
        ),
        output_path
    ]

    result = subprocess.run(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if result.returncode != 0:
        print("[TTS] ffmpeg error:")
        print(result.stderr.decode())
        return input_path

    # Clean up raw file if different from output
    if input_path != output_path:
        try:
            os.remove(input_path)
        except:
            pass

    return output_path

async def synthesize(text: str) -> str:
    """Convert text to speech, save to default file."""
    return await synthesize_to(text, DEFAULT_OUTPUT)

async def synthesize_to(text: str, filepath: str) -> str:
    """Convert text to speech with post-processing."""
    if not filepath.endswith('.mp3'):
        filepath = filepath.rsplit('.', 1)[0] + '.mp3'

    # Save raw TTS to temp file
    raw_path = filepath.replace('.mp3', '_raw.mp3')
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH)
    await communicate.save(raw_path)

    # Apply post-processing
    processed = await asyncio.to_thread(postprocess_audio, raw_path, filepath)
    return processed

def speak(text: str) -> str:
    """Synchronous wrapper."""
    return asyncio.run(synthesize(text))

if __name__ == "__main__":
    path = asyncio.run(synthesize("This is a test of the text to speech pipeline."))
    print(f"Saved to {path}")
