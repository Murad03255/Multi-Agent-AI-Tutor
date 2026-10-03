import json
import os
import sys
from dotenv import load_dotenv
from pydantic import BaseModel
from crewai import Agent, Crew, LLM, Process, Task

from memory import get_student, update_student
from tools import calculator, concept_lookup, wiki_search

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()


# ---- Structured Output Models ----

class QuizQuestion(BaseModel):
    number: int
    question: str
    options: list[str] = []
    correct_answer: str
    explanation: str


class Quiz(BaseModel):
    topic: str
    difficulty: str
    questions: list[QuizQuestion]


class EvalReport(BaseModel):
    score: int
    passed: bool
    strengths: list[str] = []
    weaknesses: list[str] = []
    feedback: str
    needs_reteach: bool = False
    reteach_topics: list[str] = []


# ---- Helper: safely extract pydantic output ----

def get_quiz(output, topic):
    if hasattr(output, "pydantic") and output.pydantic:
        return output.pydantic
    try:
        raw = str(output.raw)
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1:
            return Quiz.model_validate_json(raw[start:end])
    except Exception:
        pass
    # fallback quiz so app doesn't crash
    return Quiz(
        topic=topic,
        difficulty="Beginner",
        questions=[
            QuizQuestion(
                number=1,
                question=f"What is the main concept of {topic}?",
                options=["A) Primary working mechanism", "B) Historical myth", "C) Random occurrence", "D) None"],
                correct_answer="A",
                explanation=f"Option A correctly identifies the core of {topic}."
            ),
            QuizQuestion(
                number=2,
                question=f"In your own words, explain how {topic} works.",
                options=[],
                correct_answer=f"Explanation of {topic} mechanism with an example.",
                explanation="Checks real understanding."
            )
        ]
    )


def get_eval(output):
    if hasattr(output, "pydantic") and output.pydantic:
        return output.pydantic
    try:
        raw = str(output.raw)
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1:
            return EvalReport.model_validate_json(raw[start:end])
    except Exception:
        pass
    return EvalReport(
        score=70,
        passed=True,
        strengths=["Basic understanding demonstrated"],
        weaknesses=["More detail needed in explanations"],
        feedback="Good work! Try to add more specific details next time.",
        needs_reteach=False,
        reteach_topics=[]
    )


# ---- LLM Setup ----

def get_llm():
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("MODEL_NAME", "openrouter/deepseek/deepseek-chat")
    return LLM(model=model, api_key=api_key or "dummy", temperature=0.3)


# ---- Build the 4 CrewAI Agents ----

def build_agents(student_name, topic, level):
    llm = get_llm()
    profile = get_student(student_name)
    past = ", ".join(profile["topics"]) if profile["topics"] else "None"

    coordinator = Agent(
        role="Study Coordinator",
        goal=f"Plan a 3-step study outline for {student_name} on '{topic}' at {level} level.",
        backstory=(
            f"You are the coordinator for Leo AI Tutor. You organize study plans for students. "
            f"{student_name} has previously studied: {past}. "
            "If the topic is unclear, guide the student politely."
        ),
        tools=[concept_lookup, wiki_search],
        llm=llm,
        verbose=True
    )

    explainer = Agent(
        role="Concept Explainer",
        goal=f"Teach '{topic}' to {student_name} using simple language and real-world examples.",
        backstory=(
            "You are an excellent teacher who makes complex topics easy to understand. "
            "You use analogies and step-by-step explanations."
        ),
        tools=[concept_lookup, calculator, wiki_search],
        llm=llm,
        verbose=True
    )

    quiz_master = Agent(
        role="Quiz Master",
        goal=f"Create 2 practice questions about '{topic}' based on the lesson.",
        backstory=(
            "You create fair and clear quiz questions. "
            "Q1 is always multiple choice and Q2 is always a short answer question."
        ),
        tools=[calculator],
        llm=llm,
        verbose=True
    )

    evaluator = Agent(
        role="Evaluator",
        goal=f"Grade {student_name}'s quiz answers and give helpful feedback.",
        backstory=(
            "You are a fair and encouraging evaluator. "
            "You score answers from 0-100 and explain what the student got right or wrong."
        ),
        tools=[calculator],
        llm=llm,
        verbose=True
    )

    return coordinator, explainer, quiz_master, evaluator


# ---- Main Tutor Functions ----

def run_lesson(student_name, topic, level="Beginner"):
    coordinator, explainer, quiz_master, _ = build_agents(student_name, topic, level)

    plan_task = Task(
        description=(
            f"Create a 3-step study plan for {student_name} on '{topic}'. Level: {level}. "
            "List key terms and what the student should learn by the end."
        ),
        expected_output="A 3-step study plan with key terms and learning goals.",
        agent=coordinator
    )

    teach_task = Task(
        description=(
            f"Teach '{topic}' to {student_name} following the coordinator's plan. "
            "Use clear examples and an analogy. End with a quick summary."
        ),
        expected_output="A clear lesson with examples, analogies, and a summary.",
        agent=explainer,
        context=[plan_task]
    )

    quiz_task = Task(
        description=(
            f"Based on the lesson about '{topic}', create exactly 2 questions:\n"
            "Q1: Multiple choice with 4 options (A, B, C, D)\n"
            "Q2: Short answer / conceptual question\n"
            "Include the correct answer and a brief explanation for each."
        ),
        expected_output="A quiz with 2 questions, answer keys, and explanations.",
        agent=quiz_master,
        context=[teach_task],
        output_pydantic=Quiz
    )

    crew = Crew(
        agents=[coordinator, explainer, quiz_master],
        tasks=[plan_task, teach_task, quiz_task],
        process=Process.sequential,
        verbose=True,
        memory=True
    )
    crew.kickoff()

    quiz = get_quiz(quiz_task.output, topic)

    answer_key = ""
    for q in quiz.questions:
        answer_key += f"\nQ{q.number}: {q.question}\nCorrect: {q.correct_answer}\nExplanation: {q.explanation}\n"

    return {
        "plan": str(plan_task.output.raw),
        "lesson": str(teach_task.output.raw),
        "quiz": quiz,
        "answer_key": answer_key
    }


def grade_answers(student_name, topic, answer_key, student_answers, level="Beginner"):
    # Always build a fresh evaluator — reusing an agent from a previous crew causes errors
    _, _, _, evaluator_agent = build_agents(student_name, topic, level)

    eval_task = Task(
        description=(
            f"Grade {student_name}'s quiz answers.\n\n"
            f"QUIZ ANSWER KEY:\n{answer_key}\n\n"
            f"STUDENT'S ANSWERS:\n{student_answers}\n\n"
            "Give a score from 0-100. List what the student understood well (strengths) "
            "and what they got wrong (weaknesses). Write encouraging feedback. "
            "Set needs_reteach=True if score is below 70."
        ),
        expected_output="Score, strengths, weaknesses, feedback, and re-teach decision.",
        agent=evaluator_agent,
        output_pydantic=EvalReport
    )

    eval_crew = Crew(agents=[evaluator_agent], tasks=[eval_task], verbose=True)
    eval_crew.kickoff()

    report = get_eval(eval_task.output)

    update_student(
        name=student_name,
        topic=topic,
        score=report.score,
        strengths=report.strengths,
        weaknesses=report.weaknesses
    )

    return report


def reteach(student_name, topic, weak_areas, level="Beginner"):
    # Always build a fresh explainer — never reuse an agent from a previous crew
    _, explainer_agent, _, _ = build_agents(student_name, topic, level)

    areas = ", ".join(weak_areas) if weak_areas else "the main concepts"

    reteach_task = Task(
        description=(
            f"Give {student_name} a short remedial lesson on '{topic}'. "
            f"Focus on these specific weak areas: {areas}. "
            "Use a fresh, simple analogy. End with one easy rule to remember."
        ),
        expected_output="A short, clear remedial lesson targeting the student's weak areas.",
        agent=explainer_agent
    )

    crew = Crew(agents=[explainer_agent], tasks=[reteach_task], verbose=True)
    crew.kickoff()

    return str(reteach_task.output.raw)


# ---- CLI Mode ----

def cli_mode():
    print("=" * 55)
    print("  🦁 Leo: Multi-Agent AI Tutor (CLI Mode)")
    print("  Coordinator | Explainer | Quiz Master | Evaluator")
    print("=" * 55)

    if not os.getenv("OPENROUTER_API_KEY"):
        print("Error: OPENROUTER_API_KEY not set in .env")
        return

    name = input("\nStudent Name [Murad]: ").strip() or "Murad"
    topic = input("Topic to study [Photosynthesis]: ").strip() or "Photosynthesis"
    level = input("Level [Beginner/Intermediate/Advanced]: ").strip() or "Beginner"

    profile = get_student(name)
    if profile["sessions"] > 0:
        print(f"\nWelcome back {name}! You've done {profile['sessions']} session(s).")
        if profile["topics"]:
            print(f"Topics done: {', '.join(profile['topics'])}")

    print("\n[Step 1] Coordinator planning + Explainer teaching...")
    data = run_lesson(name, topic, level)

    print("\n--- LESSON ---")
    print(data["lesson"])

    print("\n--- QUIZ ---")
    for q in data["quiz"].questions:
        print(f"\nQ{q.number}: {q.question}")
        for opt in q.options:
            print(f"  {opt}")

    # Human-in-the-loop
    print("\n[Step 2] Your turn to answer! (Human-in-the-Loop)")
    answers = []
    for q in data["quiz"].questions:
        ans = input(f"\nAnswer for Q{q.number}: ").strip()
        answers.append(f"Q{q.number}: {ans}")

    student_submission = "\n".join(answers)

    print("\n[Step 3] Evaluator grading your answers...")
    report = grade_answers(name, topic, data["answer_key"], student_submission, level)

    print(f"\n--- RESULT: {report.score}% ({'PASSED' if report.passed else 'NEEDS REVIEW'}) ---")
    print("Strengths:", ", ".join(report.strengths) or "N/A")
    print("Weaknesses:", ", ".join(report.weaknesses) or "N/A")
    print("Feedback:", report.feedback)

    if report.needs_reteach or report.score < 70:
        weak = report.reteach_topics or report.weaknesses
        print("\n[Step 4] Adaptive Feedback Loop: Explainer re-teaching weak areas...")
        print(reteach(name, topic, weak, level))

    print("\nSession saved. See you next time!")


if __name__ == "__main__":
    cli_mode()