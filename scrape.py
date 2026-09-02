import subprocess
import numpy as np
import yt_dlp


def get_live_stream_url(youtube_url):
    """Extracts the direct raw audio stream URL from YouTube."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        return info['url']


def capture_fed_audio(youtube_url):
    stream_url = get_live_stream_url(youtube_url)

    # FFmpeg command to grab the stream, convert to 16kHz mono PCM, and output to pipe
    command = [
        'ffmpeg',
        '-i', stream_url,
        '-f', 's16le',          # Raw PCM format
        '-acodec', 'pcm_s16le',  # 16-bit encoding
        '-ar', '16000',         # 16 kHz sample rate (Required for Whisper)
        '-ac', '1',             # Mono audio
        '-'                     # Output to standard out (the pipe)
    ]

    # Open the FFmpeg process silently
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    # 16000 samples/sec * 5 seconds * 2 bytes/sample = 160,000 bytes per chunk
    chunk_size = 16000 * 5 * 2

    print("Listening to the Fed...")

    try:
        while True:
            # Read exactly 5 seconds of audio bytes
            raw_audio = process.stdout.read(chunk_size)
            if not raw_audio:
                break

            # Convert raw bytes into a NumPy array normalized between -1.0 and 1.0
            # This is the exact mathematical format faster-whisper expects
            audio_array = np.frombuffer(
                raw_audio, np.int16).astype(np.float32) / 32768.0

            # --- AT THIS POINT, YOU PASS 'audio_array' INTO FASTER-WHISPER ---
            text = whisper_model.transcribe(audio_array)
            print(text)

    except KeyboardInterrupt:
        print("Stopping stream.")
    finally:
        process.kill()


# Example usage (Replace with the actual live stream link on Fed day)
capture_fed_audio("https://www.youtube.com/watch?v=YOUR_LIVE_STREAM_ID")
