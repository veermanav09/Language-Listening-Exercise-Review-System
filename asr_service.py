
from faster_whisper import WhisperModel

# Load Whisper on CPU
model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8"
)

RELIABILITY_THRESHOLD = 75


def clamp(value):
    return max(0.0, min(1.0, value))


def transcribe_audio(audio_path: str):

    segments, info = model.transcribe(
        audio_path,
        beam_size=5
    )

    # Process all segments
    segments = list(segments)

    transcription = " ".join(
        segment.text.strip() for segment in segments
    ).strip()

    # Handle recordings with no recognized speech
    if not segments or not transcription:
        return {
            "transcribed_text": "",
            "detected_language": info.language,
            "language_probability": info.language_probability,
            "reliability_score": 0.0,
            "status": "re_record"
        }

    # Collect Whisper's quality indicators
    avg_logprob = sum(
        s.avg_logprob for s in segments
    ) / len(segments)

    avg_no_speech = sum(
        s.no_speech_prob for s in segments
    ) / len(segments)

    avg_compression = sum(
        s.compression_ratio for s in segments
    ) / len(segments)

    # Convert indicators into normalized heuristic scores
    logprob_score = clamp((avg_logprob + 1.5) / 1.5)

    speech_score = clamp(1 - avg_no_speech)

    compression_score = clamp(
        (3.0 - avg_compression) / 0.6
    )

    # Calculate provisional reliability score
    reliability = (
        0.70 * logprob_score +
        0.20 * speech_score +
        0.10 * compression_score
    ) * 100

    reliability = round(reliability, 2)

    # Decide whether the transcript can proceed
    if reliability >= RELIABILITY_THRESHOLD:
        status = "ready_for_evaluation"
    else:
        status = "re_record"

    return {
        "transcribed_text": transcription,
        "detected_language": info.language,
        "language_probability": round(
            info.language_probability, 4
        ),
        "reliability_score": reliability,
        "status": status
    }
