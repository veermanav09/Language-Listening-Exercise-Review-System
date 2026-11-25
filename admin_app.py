import streamlit as st
import json
import uuid
from pathlib import Path
import PyPDF2
import docx

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "assessments.json"
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

# Put EVERYTHING inside this function
def render_admin():
    if "admin_logged_in" not in st.session_state:
        st.session_state.admin_logged_in = False

    if not st.session_state.admin_logged_in:
        st.title("👨‍🏫 Professor Login")
        st.markdown("Please log in to access the Admin Portal.")
        
        with st.form("login_form"):
            username = st.text_input("Username", value="professor")
            password = st.text_input("Password", type="password", help="Hint: admin123")
            submit = st.form_submit_button("Login", type="primary")
            
            if submit:
                if password == "admin123":
                    st.session_state.admin_logged_in = True
                    st.rerun()
                else:
                    st.error("Invalid password. Try 'admin123'.")
        return # Use return instead of st.stop() so it doesn't break main.py

    st.title("📚 Admin: Create Assessment")
    
    def extract_text(uploaded_file):
        text = ""
        try:
            if uploaded_file.name.endswith(".pdf"):
                reader = PyPDF2.PdfReader(uploaded_file)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            elif uploaded_file.name.endswith(".docx"):
                doc = docx.Document(uploaded_file)
                for para in doc.paragraphs:
                    text += para.text + "\n"
            elif uploaded_file.name.endswith(".txt"):
                text = uploaded_file.read().decode("utf-8")
        except Exception as e:
            st.error(f"Error reading file: {e}")
        return text

    def mock_generate_questions(text, num_questions=2):
        snippet = text[:100].strip().replace("\n", " ") + "..." if text else "the provided document"
        questions = []
        for i in range(num_questions):
            questions.append({
                "question_id": f"gen_{uuid.uuid4().hex[:6]}",
                "order": i + 1,
                "question_text": f"Based on the text '{snippet}', explain the core concept {i+1}.",
                "reference_answer": f"The reference answer derived from the text regarding concept {i+1}.",
                "keywords": ["keyword1", "keyword2", "keyword3"],
                "expected_concepts": ["Expected Concept A", "Expected Concept B"],
                "difficulty": "medium",
                "max_marks": 10,
                "evaluation_criteria": {"semantic_similarity": 0.35, "keyword_coverage": 0.25, "factual_correctness": 0.30, "completeness": 0.10},
                "rubric": {"excellent": "Hits all keywords", "good": "Hits most keywords", "partial": "Hits some", "poor": "Misses concept"}
            })
        return questions

    if st.sidebar.button("Logout"):
        st.session_state.admin_logged_in = False
        st.rerun()

    col1, col2 = st.columns([2, 1])
    with col1:
        assessment_title = st.text_input("Assessment Title", placeholder="e.g., Chapter 4: Photosynthesis")
    with col2:
        target_learner = st.selectbox("Assign To", ["learner_001", "learner_002", "all"])

    uploaded_file = st.file_uploader("Upload Reference Material (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"])

    if "generated_questions" not in st.session_state:
        st.session_state.generated_questions = None

    if st.button("Extract Text & Generate Questions", type="primary"):
        if not uploaded_file or not assessment_title:
            st.warning("Please provide a title and upload a file.")
        else:
            with st.spinner("Generating..."):
                text = extract_text(uploaded_file)
                if text:
                    st.session_state.generated_questions = mock_generate_questions(text, 2)
                    st.success("Questions generated! Review them below.")

    if st.session_state.generated_questions:
        st.markdown("---")
        st.subheader("📝 Review & Approve Questions")
        
        edited_questions = []
        with st.form("review_form"):
            for i, q in enumerate(st.session_state.generated_questions):
                with st.container(border=True):
                    st.markdown(f"**Question {i+1}**")
                    q_text = st.text_area(f"Question Text", value=q["question_text"], key=f"q_{i}")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        ref_ans = st.text_area("Reference Answer", value=q["reference_answer"], key=f"a_{i}")
                        diff = st.selectbox("Difficulty", ["easy", "medium", "hard"], index=1, key=f"d_{i}")
                    with col_b:
                        marks = st.number_input("Max Marks", min_value=1, max_value=50, value=q["max_marks"], key=f"m_{i}")
                        keywords = st.text_input("Keywords (comma separated)", value=", ".join(q["keywords"]), key=f"k_{i}")
                    
                    q_copy = q.copy()
                    q_copy["question_text"] = q_text
                    q_copy["reference_answer"] = ref_ans
                    q_copy["difficulty"] = diff
                    q_copy["max_marks"] = marks
                    q_copy["keywords"] = [k.strip() for k in keywords.split(",") if k.strip()]
                    edited_questions.append(q_copy)
            
            if st.form_submit_button("✅ Approve & Publish Assessment", type="primary"):
                new_assessment = {
                    "assessment_id": f"asm_{uuid.uuid4().hex[:6]}",
                    "title": assessment_title,
                    "subject": "Uploaded Material",
                    "assigned_to": ["learner_001", "learner_002"] if target_learner == "all" else [target_learner],
                    "status": "approved",
                    "pass_threshold": 75,
                    "questions": edited_questions
                }
                
                data = {"assessments": []}
                if DATA_FILE.exists():
                    try:
                        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                    except:
                        pass
                        
                data["assessments"].append(new_assessment)
                DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
                
                st.success(f"Assessment '{assessment_title}' published!")
                st.session_state.generated_questions = None
                st.rerun()