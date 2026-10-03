import streamlit as st
from dotenv import load_dotenv

from leo import EvalReport, Quiz, grade_answers, reteach, run_lesson
from memory import get_student

load_dotenv()

st.set_page_config(page_title="Leo AI Tutor", page_icon="🦁", layout="wide")

# Session state setup
for key in ["step", "data", "report", "remedial", "topic"]:
    if key not in st.session_state:
        st.session_state[key] = None if key not in ["step", "topic"] else ("idle" if key == "step" else "")


# ---- Sidebar ----

with st.sidebar:
    st.header("👤 Student")
    student_name = st.text_input("Name", value="Murad")
    level = st.selectbox("Difficulty", ["Beginner", "Intermediate", "Advanced"])

    st.divider()

    profile = get_student(student_name)
    st.subheader("📊 Your Progress")
    col1, col2 = st.columns(2)
    col1.metric("Sessions", profile.get("sessions", 0))
    scores = profile.get("scores", [])
    avg = f"{int(sum(scores)/len(scores))}%" if scores else "N/A"
    col2.metric("Avg Score", avg)

    if profile.get("topics"):
        st.write("**Topics done:**", ", ".join(profile["topics"]))

    if profile.get("weak_areas"):
        st.write("**Need review:**")
        for w in profile["weak_areas"][:3]:
            st.write(f"- {w}")

    st.divider()
    st.subheader("🤖 Agents in Leo")
    st.write("🎯 **Coordinator** — Builds study plan")
    st.write("👨‍🏫 **Explainer** — Teaches the topic")
    st.write("📝 **Quiz Master** — Creates quiz questions")
    st.write("📊 **Evaluator** — Grades and gives feedback")

    if st.button("🔄 Reset"):
        st.session_state.step = "idle"
        st.session_state.data = None
        st.session_state.report = None
        st.session_state.remedial = None
        st.session_state.topic = ""
        st.rerun()


# ---- Main Area ----

st.title("🦁 Leo: Multi-Agent AI Tutor")
st.caption("CrewAI | Sequential handoffs | Student memory | Human-in-the-Loop | Adaptive feedback loop")


# Step 0: Pick a topic
if st.session_state.step == "idle":
    st.subheader("What do you want to learn today?")

    col_a, col_b = st.columns([4, 1])
    with col_a:
        topic_input = st.text_input("Topic:", value=st.session_state.topic or "Photosynthesis", label_visibility="collapsed")
    with col_b:
        go = st.button("🚀 Start", type="primary", use_container_width=True)

    st.write("Quick picks:")
    quick_cols = st.columns(5)
    for i, s in enumerate(["Photosynthesis", "Binary Search", "Gravity", "Mitosis", "Recursion"]):
        if quick_cols[i].button(s, key=f"q_{s}", use_container_width=True):
            topic_input = s
            st.session_state.topic = s
            go = True

    if go and topic_input.strip():
        st.session_state.topic = topic_input.strip()
        with st.spinner("Agents working: Coordinator → Explainer → Quiz Master..."):
            try:
                result = run_lesson(student_name, topic_input.strip(), level)
                st.session_state.data = result
                st.session_state.step = "answering"
                st.rerun()
            except Exception as e:
                st.error(f"Something went wrong: {e}")
    elif go:
        st.warning("Please enter a topic first.")


# Step 1 & 2: Show lesson and quiz form
if st.session_state.step in ["answering", "done"]:
    data = st.session_state.data
    topic = st.session_state.topic

    with st.expander("🎯 **Agent 1 (Coordinator) — Study Plan**", expanded=True):
        st.write(data["plan"])

    st.subheader("👨‍🏫 Agent 2 (Explainer) — Lesson")
    st.write(data["lesson"])
    st.divider()

    st.subheader("📝 Agent 3 (Quiz Master) — Practice Questions")
    quiz: Quiz = data["quiz"]

    if st.session_state.step == "answering":
        st.info("✋ **Human-in-the-Loop:** Answer below and submit to the Evaluator agent.")

        with st.form("quiz"):
            answers = {}
            for q in quiz.questions:
                st.write(f"**Q{q.number}:** {q.question}")
                if q.options:
                    answers[q.number] = st.radio("Options:", q.options, key=f"a_{q.number}")
                else:
                    answers[q.number] = st.text_area("Your answer:", key=f"a_{q.number}")
                st.write("")

            submit = st.form_submit_button("📤 Submit to Evaluator", type="primary", use_container_width=True)

        if submit:
            sub_text = "\n".join([f"Q{n}: {a}" for n, a in answers.items()])
            with st.spinner("Agent 4 (Evaluator) is grading your answers..."):
                report = grade_answers(student_name, topic, data["answer_key"], sub_text, level)
                st.session_state.report = report

                # Adaptive feedback loop — triggers if score < 70
                if report.needs_reteach or report.score < 70:
                    with st.spinner("🔄 Feedback loop: Explainer is re-teaching your weak areas..."):
                        weak = report.reteach_topics or report.weaknesses
                        st.session_state.remedial = reteach(student_name, topic, weak, level)

                st.session_state.step = "done"
                st.rerun()


# Step 3: Show evaluation result
if st.session_state.step == "done":
    report: EvalReport = st.session_state.report

    st.subheader("📊 Agent 4 (Evaluator) — Your Results")

    if report.passed:
        st.success(f"### {report.score}% — PASSED ✅")
    else:
        st.warning(f"### {report.score}% — NEEDS REVIEW ⚠️")

    col_l, col_r = st.columns(2)
    with col_l:
        st.write("**What you got right (Strengths):**")
        for s in report.strengths:
            st.write(f"✅ {s}")
    with col_r:
        st.write("**What needs work (Weaknesses):**")
        for w in report.weaknesses:
            st.write(f"❌ {w}")

    st.write("**Feedback from your coach:**")
    st.info(report.feedback)

    if st.session_state.remedial:
        st.warning("### 🔄 Adaptive Feedback Loop")
        st.caption("Score was below 70%, so the Explainer agent is re-teaching the weak concepts.")
        st.write(st.session_state.remedial)

    st.success("Session saved to your profile!")

    c1, c2 = st.columns(2)
    if c1.button("📖 New Topic", type="primary", use_container_width=True):
        st.session_state.update(step="idle", data=None, report=None, remedial=None, topic="")
        st.rerun()
    if c2.button("🔁 Try Again", use_container_width=True):
        st.session_state.update(step="idle", data=None, report=None, remedial=None)
        st.rerun()
