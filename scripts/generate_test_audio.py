"""Generate test WAV audio files for testing.

Creates sine wave, silence, and noise samples as valid WAV files.
These are NOT real speech but valid audio for testing the pipeline.
"""

import struct
import wave
from pathlib import Path

import numpy as np


SAMPLE_RATE = 16000
DURATION_SECONDS = 3.0


def generate_sine_wave(
    frequency: float = 440.0,
    duration: float = DURATION_SECONDS,
    sample_rate: int = SAMPLE_RATE,
    amplitude: float = 0.5,
) -> np.ndarray:
    """Generate a sine wave signal."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


def generate_silence(
    duration: float = DURATION_SECONDS,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Generate silence."""
    return np.zeros(int(sample_rate * duration), dtype=np.float32)


def generate_noise(
    duration: float = DURATION_SECONDS,
    sample_rate: int = SAMPLE_RATE,
    amplitude: float = 0.1,
) -> np.ndarray:
    """Generate white noise."""
    rng = np.random.default_rng(42)
    return (amplitude * rng.standard_normal(int(sample_rate * duration))).astype(np.float32)


def generate_mixed_signal(
    duration: float = DURATION_SECONDS,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Generate a signal with sine wave + noise, simulating real-ish audio."""
    sine = generate_sine_wave(frequency=300, duration=duration, sample_rate=sample_rate, amplitude=0.3)
    noise = generate_noise(duration=duration, sample_rate=sample_rate, amplitude=0.05)
    return (sine + noise).astype(np.float32)


def save_wav(
    data: np.ndarray,
    filepath: Path,
    sample_rate: int = SAMPLE_RATE,
) -> None:
    """Save numpy array as a 16-bit PCM WAV file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    pcm_data = (data * 32767).astype(np.int16)
    with wave.open(str(filepath), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data.tobytes())


def main() -> None:
    """Generate all test audio files."""
    output_dir = Path(__file__).parent.parent / "tests" / "fixtures" / "audio_samples"

    samples = {
        "sine_440hz.wav": generate_sine_wave(frequency=440.0),
        "sine_300hz.wav": generate_sine_wave(frequency=300.0),
        "silence.wav": generate_silence(),
        "noise.wav": generate_noise(),
        "mixed.wav": generate_mixed_signal(),
        "short_sine.wav": generate_sine_wave(frequency=440.0, duration=0.5),
        "long_sine.wav": generate_sine_wave(frequency=440.0, duration=10.0),
    }

    for filename, data in samples.items():
        filepath = output_dir / filename
        save_wav(data, filepath)
        print(f"Generated: {filepath} ({len(data)} samples, {len(data)/SAMPLE_RATE:.1f}s)")

    print(f"\nAll {len(samples)} test audio files generated in {output_dir}")


if __name__ == "__main__":
    main()
