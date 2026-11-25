import streamlit as st
import json
import uuid
from pathlib import Path
from datetime import datetime

try:
    from gtts import gTTS
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "assessments.json"
RECORDING_DIR = BASE_DIR / "recordings"
TTS_DIR = BASE_DIR / "assets" / "tts"
RECORDING_DIR.mkdir(parents=True, exist_ok=True)
TTS_DIR.mkdir(parents=True, exist_ok=True)

def render_learner():
    def load_assessments():
        if not DATA_FILE.exists():
            return {"assessments": []}
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except:
            return {"assessments": []}

    def save_recording(audio_bytes: bytes) -> Path:
        fname = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}.wav"
        p = RECORDING_DIR / fname
        p.write_bytes(audio_bytes)
        return p

    def question_audio(q: dict) -> Path | None:
        if not TTS_AVAILABLE: return None
        out = TTS_DIR / f"{q['question_id']}.mp3"
        if not out.exists():
            try:
                gTTS(text=q["question_text"], lang="en", slow=False).save(str(out))
            except Exception as e:
                st.error(f"TTS Error: {e}")
                return None
        return out

    def transcribe_and_evaluate(audio_path: Path, question: dict, threshold: float) -> dict:
        import random
        score = round(random.uniform(60, 98), 1)
        return {
            "status": "evaluated",
            "reliability": 0.86,
            "transcript": "(mock transcript)",
            "score": score,
            "passed": score >= threshold,
            "feedback": {"correct": ["Good"], "incorrect": [], "missing": ["More detail"], "improve": "Study more"},
        }

    def init_state(assessment_id: str):
        key = f"session_{assessment_id}"
        if key not in st.session_state:
            st.session_state[key] = {"index": 0, "results": {}, "finished": False}
        return st.session_state[key]

    data = load_assessments()
    assessments = data.get("assessments", [])

    st.title("🎧 ListenUp — Learner Portal")
    learner_id = st.sidebar.selectbox("Signed in as:", ["learner_001", "learner_002"])
    assigned = [a for a in assessments if learner_id in a.get("assigned_to", [])]

    if not assigned:
        st.info("No assessments assigned to you yet. Ask your admin.")
        return

    selected = st.sidebar.selectbox("Assessment:", assigned, format_func=lambda a: a["title"])
    threshold = selected.get("pass_threshold", 75)
    questions = sorted(selected["questions"], key=lambda q: q.get("order", q["question_id"]))
    state = init_state(selected["assessment_id"])

    answered = len(state["results"])
    total = len(questions)
    st.progress(answered / total if total > 0 else 0, text=f"Progress: {answered}/{total} questions answered")
    st.markdown("---")

    if state["finished"]:
        st.header("✅ Assessment complete")
        total_score = sum(r["score"] for r in state["results"].values()) / max(len(state["results"]), 1)
        passed_all = all(r["passed"] for r in state["results"].values())
        col1, col2, col3 = st.columns(3)
        col1.metric("Average score", f"{total_score:.1f}/100")
        col2.metric("Outcome", "PASS" if passed_all else "FAIL")
        col3.metric("Questions answered", f"{answered}/{total}")

        st.subheader("Per-question breakdown")
        for q in questions:
            r = state["results"].get(q["question_id"])
            if r:
                with st.expander(f"{'✅' if r['passed'] else '❌'} Q: {q['question_text'][:70]}… — {r['score']}/100"):
                    st.write("**Transcript:**", r["transcript"])
                    st.json(r["feedback"])

        if st.button("Restart assessment"):
            state.update({"index": 0, "results": {}, "finished": False})
            st.rerun()
        return

    q = questions[state["index"]]
    q_num = state["index"] + 1

    st.subheader(f"Question {q_num} of {total}")
    st.caption(f"Difficulty: {q['difficulty']} · Max marks: {q['max_marks']}")

    tts_path = question_audio(q)
    col_q, col_play = st.columns([4, 1])
    with col_q:
        st.markdown(f"### {q['question_text']}")
    with col_play:
        if tts_path and tts_path.exists():
            st.audio(str(tts_path), format="audio/mp3")

    st.write("") 
    st.markdown("**Your spoken answer:**")
    audio_input = st.audio_input(f"Record your answer for Q{q_num}", key=f"rec_{q['question_id']}")
    submit = st.button("Submit answer", type="primary", disabled=audio_input is None)

    if submit and audio_input is not None:
        path = save_recording(audio_input.getvalue())
        with st.spinner("Transcribing and evaluating…"):
            result = transcribe_and_evaluate(path, q, threshold)

        state["results"][q["question_id"]] = result
        if state["index"] + 1 < total:
            state["index"] += 1
        else:
            state["finished"] = True
        st.rerun()