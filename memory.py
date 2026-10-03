import json
import os

MEMORY_FILE = "student_memory.json"


def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_memory(data):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_student(name):
    data = load_memory()
    key = name.lower().strip()

    if key not in data:
        # New student profile
        data[key] = {
            "name": name,
            "sessions": 0,
            "topics": [],
            "scores": [],
            "strengths": [],
            "weak_areas": []
        }
        save_memory(data)
        return data[key]

    # Handle old format keys from previous runs (backward compatibility)
    profile = data[key]
    if "topics_studied" in profile and "topics" not in profile:
        profile["topics"] = profile.pop("topics_studied", [])
    if "sessions_count" in profile and "sessions" not in profile:
        profile["sessions"] = profile.pop("sessions_count", 0)
    if "recent_scores" in profile and "scores" not in profile:
        profile["scores"] = profile.pop("recent_scores", [])
    if "known_strengths" in profile and "strengths" not in profile:
        profile["strengths"] = profile.pop("known_strengths", [])
    if "areas_to_improve" in profile and "weak_areas" not in profile:
        profile["weak_areas"] = profile.pop("areas_to_improve", [])

    # Make sure all keys exist even if missing
    profile.setdefault("topics", [])
    profile.setdefault("sessions", 0)
    profile.setdefault("scores", [])
    profile.setdefault("strengths", [])
    profile.setdefault("weak_areas", [])

    data[key] = profile
    save_memory(data)
    return profile


def update_student(name, topic, score, strengths, weaknesses):
    data = load_memory()
    key = name.lower().strip()

    # Make sure profile exists and is up to date
    profile = get_student(name)
    profile["sessions"] = profile.get("sessions", 0) + 1

    if topic not in profile.get("topics", []):
        profile.setdefault("topics", []).append(topic)

    profile.setdefault("scores", []).append(score)

    for s in strengths:
        if s and s not in profile.get("strengths", []):
            profile.setdefault("strengths", []).append(s)

    profile["weak_areas"] = weaknesses

    data[key] = profile
    save_memory(data)
