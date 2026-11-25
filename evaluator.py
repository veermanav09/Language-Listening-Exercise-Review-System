import math
import re
from collections import Counter
from difflib import SequenceMatcher

DEFAULT_WEIGHTS = {"semantic": 0.35, "keywords": 0.25, "factual": 0.30, "completeness": 0.10}
PASS_THRESHOLD = 0.90  # Admin-configurable
NEG = {"not", "no", "never", "cannot", "cant", "without", "neither", "nor"}
STOP = set("a an the of to and or in on for is are was were be been it its that this with as by at from can".split())

# ---------- text helpers ----------
def _tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower().replace("n't", " not"))

def _stem(w):
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w

def _stems(text):
    return [_stem(t) for t in _tokens(text) if t not in STOP]

# ---------- 1. semantic similarity ----------
_model = None
def _semantic(answer, reference):
    global _model
    try:
        if _model is None:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
        from sentence_transformers import util
        e = _model.encode([answer, reference], convert_to_tensor=True)
        cos = float(util.cos_sim(e[0], e[1]))
        return max(0.0, min(1.0, (cos - 0.2) / 0.7)), "embeddings"  # provisional rescale
    except Exception:  # fallback: bag-of-words cosine
        a, r = Counter(_stems(answer)), Counter(_stems(reference))
        dot = sum(a[k] * r[k] for k in a)
        n = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in r.values()))
        return (dot / n if n else 0.0), "bow-fallback"

# ---------- 2. keyword / concept coverage ----------
def _concept_match(concept, ans_tokens):
    """concept may list synonyms with '|'. Returns (found, negated)."""
    for alt in concept.split("|"):
        cs = _stems(alt)
        if not cs:
            continue
        for i in range(len(ans_tokens)):
            window = ans_tokens[i : i + len(cs)]
            if len(window) == len(cs) and all(
                x == y or (len(y) > 4 and SequenceMatcher(None, x, y).ratio() > 0.85)
                for x, y in zip(window, cs)
            ):
                before = ans_tokens[max(0, i - 3) : i]
                return True, any(b in NEG for b in before)
    return False, False

def _keywords(answer, concepts):
    raw = _tokens(answer)
    toks = [_stem(t) if t not in NEG else t for t in raw if t not in STOP or t in NEG]
    correct, missing, incorrect = [], [], []
    for c in concepts:
        found, neg = _concept_match(c, [t for t in toks])
        label = c.split("|")[0]
        (incorrect if found and neg else correct if found else missing).append(label)
    cov = len(correct) / len(concepts) if concepts else 1.0
    return cov, correct, missing, incorrect

# ---------- 3/4. factual + completeness ----------
def _completeness(answer, reference):
    ref, ans = set(_stems(reference)), set(_stems(answer))
    return len(ref & ans) / len(ref) if ref else 1.0

def _factual_heuristic(sem, incorrect):
    # Without an LLM: no detected contradictions -> trust semantic proxy; each negated concept costs 0.5.
    return max(0.0, sem - 0.5 * len(incorrect))

# ---------- main entry ----------
def evaluate(question_id, transcribed_text, reference_answer, expected_keywords,
             max_marks, weights=None, pass_threshold=PASS_THRESHOLD, llm_judge=None):
    """
    llm_judge (optional): callable(transcribed_text, reference_answer, expected_keywords) -> dict with
      {"factual": 0-1, "completeness": 0-1, "incorrect_concepts": [str], "critical_contradiction": bool}
    Plug in any LLM; the final score is always computed here, never by the LLM alone.
    """
    w = weights or DEFAULT_WEIGHTS
    text = (transcribed_text or "").strip()
    if not text:
        return {"question_id": question_id, "score": 0.0, "max_marks": max_marks, "percentage": 0.0,
                "passed": False, "feedback": "No answer detected.", "correct_concepts": [],
                "missing_concepts": list(expected_keywords), "incorrect_concepts": [],
                "components": {}, "critical_contradiction": False}

    sem, sem_method = _semantic(text, reference_answer)
    cov, correct, missing, incorrect = _keywords(text, expected_keywords)
    comp = _completeness(text, reference_answer)
    fact, critical, method = _factual_heuristic(sem, incorrect), bool(incorrect), "heuristic"

    if llm_judge:
        j = llm_judge(text, reference_answer, expected_keywords)
        fact, comp = j.get("factual", fact), j.get("completeness", comp)
        incorrect = list(dict.fromkeys(incorrect + j.get("incorrect_concepts", [])))
        critical, method = bool(j.get("critical_contradiction")), "llm"

    pct = (w["semantic"] * sem + w["keywords"] * cov + w["factual"] * fact + w["completeness"] * comp)
    pct = max(0.0, min(1.0, pct / sum(w.values())))
    passed = pct >= pass_threshold

    parts = []
    if correct: parts.append("Covered well: " + ", ".join(correct) + ".")
    if missing: parts.append("Missing: " + ", ".join(missing) + ".")
    if incorrect: parts.append("Incorrect/contradicted: " + ", ".join(incorrect) + ".")
    parts.append("Great answer!" if passed else "Revise the missing/incorrect points and try to cover the full reference idea.")

    return {
        "question_id": question_id,
        "score": round(pct * max_marks, 2),
        "max_marks": max_marks,
        "percentage": round(pct * 100, 1),
        "passed": passed,
        "feedback": " ".join(parts),
        "correct_concepts": correct,
        "missing_concepts": missing,
        "incorrect_concepts": incorrect,
        "critical_contradiction": critical,
        "components": {"semantic": round(sem, 3), "keywords": round(cov, 3),
                       "factual": round(fact, 3), "completeness": round(comp, 3),
                       "semantic_method": sem_method, "factual_method": method},
    }

# ---------- optional FastAPI wrapper: uvicorn evaluator:app --port 8001 ----------
try:
    from fastapi import FastAPI
    from pydantic import BaseModel

    class EvalRequest(BaseModel):
        question_id: str
        transcribed_text: str
        reference_answer: str
        expected_keywords: list[str]
        max_marks: float = 10

    app = FastAPI()

    @app.post("/evaluate")
    def evaluate_endpoint(r: EvalRequest):
        return evaluate(r.question_id, r.transcribed_text, r.reference_answer,
                        r.expected_keywords, r.max_marks)
except ImportError:
    pass

if __name__ == "__main__":
    ref = "Artificial intelligence enables computers to perform tasks that normally require human intelligence."
    kws = ["computers", "tasks", "human intelligence|human-like intelligence"]
    for t in ["Artificial intelligence lets machines do tasks that need human intelligence.",
              "AI is about computers but does not need human intelligence.",
              "It is a kind of database."]:
        print(evaluate("q1", t, ref, kws, 10), "\n")