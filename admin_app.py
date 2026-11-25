import streamlit as st
import json
import uuid
from pathlib import Path
import PyPDF2
import docx
import os
from groq import Groq
from dotenv import load_dotenv

# Load Groq API Key
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "assessments.json"
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

def render_admin():
    if "admin_logged_in" not in st.session_state:
        st.session_state.admin_logged_in = False

    # ---------------- LOGIN ----------------
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
        return

    st.title("📚 Admin: Create Assessment")
    
    # ---------------- HELPER FUNCTIONS ----------------
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

    def generate_questions_llm(text, num_questions=2):
        if not GROQ_API_KEY:
            st.error("GROQ_API_KEY is missing. Please check your .env file.")
            return []
            
        client = Groq(api_key=GROQ_API_KEY)
        truncated_text = text[:5000] # Limit text to avoid token limits
        
        prompt = f"""
        You are an expert professor. Based on the following reference text, generate {num_questions} assessment questions.
        
        Return the response ONLY as a valid JSON array. Do not include markdown formatting like ```json.
        Each object in the array must have this exact structure:
        {{
            "question_id": "unique_string",
            "order": integer,
            "question_text": "string",
            "reference_answer": "string",
            "keywords": ["string", "string", "string"],
            "expected_concepts": ["string", "string"],
            "difficulty": "easy" | "medium" | "hard",
            "max_marks": integer,
            "evaluation_criteria": {{
                "semantic_similarity": 0.35,
                "keyword_coverage": 0.25,
                "factual_correctness": 0.30,
                "completeness": 0.10
            }},
            "rubric": {{
                "excellent": "string",
                "good": "string",
                "partial": "string",
                "poor": "string"
            }}
        }}

        Reference Text:
        {truncated_text}
        """
        
        try:
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="openai/gpt-oss-20b",
                temperature=0.3,
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Clean up potential markdown formatting
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
                
            questions = json.loads(result_text.strip())
            
            # Ensure unique IDs
            for i, q in enumerate(questions):
                q["question_id"] = f"gen_{uuid.uuid4().hex[:6]}"
                q["order"] = i + 1
                
            return questions
            
        except Exception as e:
            st.error(f"Failed to generate questions: {e}")
            return []

    # ---------------- UI ----------------
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
            with st.spinner("AI is reading the document and generating questions..."):
                text = extract_text(uploaded_file)
                if text:
                    st.session_state.generated_questions = generate_questions_llm(text, 2)
                    if st.session_state.generated_questions:
                        st.success("Questions generated! Review them below.")
                    else:
                        st.warning("No questions could be generated. Check the text format.")

    # ---------------- REVIEW & APPROVE ----------------
    if st.session_state.generated_questions:
        st.markdown("---")
        st.subheader("📝 Review & Approve Questions")
        
        edited_questions = []
        with st.form("review_form"):
            for i, q in enumerate(st.session_state.generated_questions):
                with st.container(border=True):
                    st.markdown(f"**Question {i+1}**")
                    q_text = st.text_area(f"Question Text", value=q.get("question_text", ""), key=f"q_{i}")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        ref_ans = st.text_area("Reference Answer", value=q.get("reference_answer", ""), key=f"a_{i}")
                        diff = st.selectbox("Difficulty", ["easy", "medium", "hard"], index=1, key=f"d_{i}")
                    with col_b:
                        marks = st.number_input("Max Marks", min_value=1, max_value=50, value=int(q.get("max_marks", 10)), key=f"m_{i}")
                        keywords = st.text_input("Keywords (comma separated)", value=", ".join(q.get("keywords", [])), key=f"k_{i}")
                    
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