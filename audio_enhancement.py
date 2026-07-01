"""
Advanced audio preprocessing and enhancement for better Whisper transcription
- Noise reduction
- Volume normalization
- Speech enhancement
- Audio validation
"""

import numpy as np
import librosa
import soundfile as sf
import tempfile
import os
from scipy import signal
from scipy.fft import fft, fftfreq


def reduce_noise_spectral_subtraction(audio_path, output_path, noise_factor=1.5):
    """
    Reduce noise using spectral subtraction technique
    Works by subtracting noise spectrum from audio spectrum
    """
    try:
        # Load audio
        y, sr = librosa.load(audio_path, sr=16000)
        
        # Compute STFT
        D = librosa.stft(y)
        magnitude = np.abs(D)
        phase = np.angle(D)
        
        # Estimate noise from first 0.5 seconds (assumes silence/low speech at start)
        noise_duration_frames = int(sr * 0.5 / 512)  # 0.5 sec at 16kHz
        noise_spectrum = np.median(magnitude[:, :max(1, noise_duration_frames)], axis=1, keepdims=True)
        
        # Spectral subtraction
        magnitude_denoised = magnitude - (noise_factor * noise_spectrum)
        magnitude_denoised = np.maximum(magnitude_denoised, 0.1 * magnitude)  # Prevent over-subtraction
        
        # Reconstruct
        D_denoised = magnitude_denoised * np.exp(1j * phase)
        y_denoised = librosa.istft(D_denoised)
        
        # Save output
        sf.write(output_path, y_denoised, sr)
        return output_path, True
    except Exception as e:
        print(f"⚠️ Spectral subtraction failed: {e}")
        return audio_path, False


def normalize_audio(audio_path, target_db=-20.0):
    """
    Normalize audio loudness to consistent level using loudness normalization
    Helps speech detection in whisper
    """
    try:
        y, sr = librosa.load(audio_path, sr=16000)
        
        # Calculate current loudness (LUFS-like)
        S = librosa.feature.melspectrogram(y=y, sr=sr)
        loudness = -20 * np.log10(np.sqrt(np.mean(S**2)) + 1e-9)
        
        # Adjust gain
        gain = 10 ** ((target_db - loudness) / 20)
        y_normalized = np.clip(y * gain, -1.0, 1.0)
        
        # Save
        sf.write(audio_path, y_normalized, sr)
        return True
    except Exception as e:
        print(f"⚠️ Normalization failed: {e}")
        return False


def enhance_speech(audio_path):
    """
    Enhance speech using a bandpass filter
    Keeps voice frequencies between 300Hz and 8kHz while removing rumble and hiss
    """
    try:
        y, sr = librosa.load(audio_path, sr=16000)
        if y.size == 0:
            print("⚠️ Speech enhancement skipped: empty audio")
            return False

        nyquist = sr / 2.0
        low_cut = 300.0
        high_cut = min(8000.0, nyquist - 100.0)

        if high_cut <= low_cut or high_cut <= 0:
            print(f"⚠️ Speech enhancement skipped: invalid cutoff values low={low_cut}, high={high_cut}, sr={sr}")
            return False

        sos = signal.butter(5, [low_cut, high_cut], 'bandpass', fs=sr, output='sos')
        y_filtered = signal.sosfilt(sos, y)

        sf.write(audio_path, y_filtered, sr)
        return True
    except Exception as e:
        print(f"⚠️ Speech enhancement failed: {e}")
        return False


def apply_compression(audio_path):
    """
    Apply audio compression to even out volume peaks
    Helps with consistent speech detection
    """
    try:
        y, sr = librosa.load(audio_path, sr=16000)
        
        # Simple RMS-based compression
        frame_length = 2048
        hop_length = 512
        
        # Calculate RMS per frame
        S = librosa.feature.melspectrogram(y=y, sr=sr, n_fft=frame_length, hop_length=hop_length)
        rms = np.sqrt(np.mean(S**2, axis=0))
        
        # Smooth RMS
        rms_smooth = np.convolve(rms, np.ones(5)/5, mode='same')
        
        # Target compression ratio 4:1
        threshold = np.median(rms_smooth)
        ratio = 4.0
        
        # Simple gain reduction based on loudness
        gain = np.ones(len(y))
        for i, rms_val in enumerate(rms_smooth):
            if rms_val > threshold:
                gain_reduction = 1 - (rms_val - threshold) / (ratio * (rms_val - threshold + 1e-9))
                start_idx = i * hop_length
                end_idx = min((i + 1) * hop_length, len(y))
                gain[start_idx:end_idx] = gain_reduction
        
        y_compressed = y * gain
        y_compressed = np.clip(y_compressed, -1.0, 1.0)
        
        sf.write(audio_path, y_compressed, sr)
        return True
    except Exception as e:
        print(f"⚠️ Compression failed: {e}")
        return False


def validate_audio_content(audio_path):
    """
    Validate that audio contains actual speech/content
    Returns True if audio has sufficient speech-like content
    """
    try:
        y, sr = librosa.load(audio_path, sr=16000)
        
        # Check 1: Duration
        duration = len(y) / sr
        if duration < 0.5:
            print(f"⚠️ Audio too short ({duration:.2f}s)")
            return False
        
        # Check 2: RMS energy
        rms = np.sqrt(np.mean(y**2))
        if rms < 0.01:  # Too quiet
            print(f"⚠️ Audio too quiet (RMS: {rms:.4f})")
            return False
        
        # Check 3: Speech-like energy distribution
        # Speech typically has energy in 300Hz-8000Hz range
        S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128)
        # Check middle frequency bins (typically where speech is)
        speech_freqs = S[30:100, :]  # ~300Hz to 8kHz in mel scale
        speech_energy = np.mean(speech_freqs)
        total_energy = np.mean(S)
        
        if speech_energy < 0.1 * total_energy:
            print(f"⚠️ Low speech-like energy")
            return False
        
        # Check 4: Silence percentage
        energy_per_frame = np.sqrt(np.mean(S, axis=0))
        threshold = 0.1 * np.max(energy_per_frame)
        silent_frames = np.sum(energy_per_frame < threshold)
        silence_ratio = silent_frames / len(energy_per_frame)
        
        if silence_ratio > 0.7:  # More than 70% silence
            print(f"⚠️ Too much silence ({silence_ratio*100:.1f}%)")
            return False
        
        print(f"✅ Audio validation passed (duration: {duration:.2f}s, RMS: {rms:.4f})")
        return True
        
    except Exception as e:
        print(f"⚠️ Audio validation error: {e}")
        return False


def process_audio_pipeline(audio_path):
    """
    Complete audio enhancement pipeline
    1. Reduce noise
    2. Enhance speech
    3. Normalize volume
    4. Apply compression
    5. Validate
    """
    print(f"🎙️ Starting audio enhancement pipeline...")
    
    try:
        # Step 1: Noise reduction
        print(f"  1️⃣ Reducing noise...")
        process_audio_pipeline.reduce_noise_spectral_subtraction(audio_path, audio_path)
        
        # Step 2: Speech enhancement (high/low pass filter)
        print(f"  2️⃣ Enhancing speech frequencies...")
        enhance_speech(audio_path)
        
        # Step 3: Compression
        print(f"  3️⃣ Compressing dynamic range...")
        apply_compression(audio_path)
        
        # Step 4: Normalize loudness
        print(f"  4️⃣ Normalizing volume...")
        normalize_audio(audio_path)
        
        # Step 5: Validate
        print(f"  5️⃣ Validating audio quality...")
        is_valid = validate_audio_content(audio_path)
        
        if is_valid:
            print(f"✅ Audio enhancement complete!")
            return True
        else:
            print(f"⚠️ Audio quality may be poor, but proceeding...")
            return True  # Still try to transcribe
            
    except Exception as e:
        print(f"❌ Audio pipeline error: {e}")
        return False


# Make reduce_noise accessible at module level
process_audio_pipeline.reduce_noise_spectral_subtraction = reduce_noise_spectral_subtraction
