#!/usr/bin/env python3
"""
Canvas Study Agent — Web UI
Run: python3 app.py
"""

from __future__ import annotations

import sys
import tempfile
import threading
import webbrowser
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

import study_agent as sa

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

PORT = 5001


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _state_dir(key: str) -> Path:
    return BASE_DIR / "state" / key


def _safe_find_topic(exam_map: dict[str, Any], query: str | None) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return sa.find_topic(exam_map, query), None
    except SystemExit as exc:
        return None, str(exc)


def _build_teach_payload(topic: dict[str, Any], course_type: str) -> dict[str, Any]:
    key_sentences = sa.extract_key_sentences(topic)
    if key_sentences:
        explanation = (
            f"Treat {topic['topic']} as a high-yield idea you need to define, recognize in context, "
            f"and apply. The course evidence points to these anchors: {' '.join(key_sentences[:2])}"
        )
    else:
        explanation = (
            f"Treat {topic['topic']} as a testable idea. Your job is to explain what it means, "
            f"when it applies, and what an instructor could ask you to do with it."
        )

    core_ideas: list[str] = list(key_sentences[:4]) or [s["snippet"] for s in topic["sources"][:4]]
    if course_type == "quantitative":
        formulas = sa.formula_lines(topic)
        if formulas:
            core_ideas.append("Formula/equation cues from the files: " + " | ".join(formulas))
        else:
            core_ideas.append("Memorize the givens, target unknown, method, and final interpretation.")
    elif course_type == "reading-heavy":
        core_ideas.append("Connect the definition to themes, arguments, evidence, and comparisons.")

    worked_example = (
        f"1. Identify what the problem is asking about {topic['topic']}. "
        "2. Write the known values or assumptions. "
        "3. Choose the formula or rule. "
        "4. Substitute carefully. "
        "5. Check units/signs and explain the result."
    ) if course_type == "quantitative" else (
        f"1. State a clear definition of {topic['topic']}. "
        "2. Add the course-specific evidence or example. "
        "3. Explain the consequence, comparison, or why the idea matters. "
        "4. End with a direct answer to the prompt."
    )

    traps = [
        f"Giving a vague definition of {topic['topic']} without course-specific language.",
        "Recognizing the term but failing to apply it to a new problem, passage, or scenario.",
        "Ignoring the source context that made the topic high-priority.",
    ]
    if course_type == "quantitative":
        traps.append("Skipping units, assumptions, or the interpretation after the calculation.")
    if course_type == "reading-heavy":
        traps.append("Listing facts instead of making a comparison, argument, or evidence-backed claim.")

    return {
        "topic": topic["topic"],
        "topic_key": topic["topic_key"],
        "priority": topic["priority"],
        "score": topic["score"],
        "confidence": topic["confidence"],
        "rationale": topic["rationale"],
        "explanation": explanation,
        "core_ideas": core_ideas,
        "question_styles": sa.likely_question_templates(topic, course_type),
        "worked_example": worked_example,
        "traps": traps,
        "quiz": sa.make_quiz_questions([topic], course_type, count=3),
        "spaced_rep": [
            f"Tomorrow: define {topic['topic']} without looking.",
            f"In 3 days: answer one likely exam-style question about {topic['topic']}.",
            f"In 7 days: compare {topic['topic']} with another high-yield topic from the map.",
        ],
        "sources": topic["sources"][:5],
    }


def _practice_dir(state_dir: Path) -> Path:
    d = state_dir / "practice_sets"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# routes — pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# routes — courses & indexing
# ---------------------------------------------------------------------------

@app.route("/api/courses")
def api_courses():
    canvas_root = BASE_DIR / "canvas_files"
    courses = []
    if canvas_root.exists():
        for d in sorted(canvas_root.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                key = d.name.lower().replace(" ", "-")
                state_dir = _state_dir(key)
                indexed = (state_dir / "exam_map.json").exists()
                file_count = sum(1 for f in d.rglob("*") if f.is_file() and not f.name.startswith("."))
                courses.append({
                    "name": d.name,
                    "key": key,
                    "course_dir": str(d),
                    "state_dir": str(state_dir),
                    "indexed": indexed,
                    "file_count": file_count,
                })
    return jsonify(courses)


@app.route("/api/index", methods=["POST"])
def api_index():
    body = request.json or {}
    course_dir = Path(body["course_dir"])
    state_dir = Path(body["state_dir"])
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        idx = sa.make_index(course_dir, state_dir)
        exam_map = sa.build_exam_map(idx, state_dir)
        return jsonify({
            "ok": True,
            "file_count": len(idx.get("files", [])),
            "topic_count": len(exam_map.get("topics", [])),
            "course_type": exam_map.get("course_type", "mixed"),
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# routes — topics & study
# ---------------------------------------------------------------------------

@app.route("/api/topics")
def api_topics():
    state_dir = Path(request.args["state"])
    limit = int(request.args.get("limit", 25))
    exam_map = sa.load_exam_map(state_dir)
    topics = exam_map.get("topics", [])[:limit]
    progress = sa.load_progress(state_dir)
    covered = set(progress.get("covered_topics", {}).keys())
    for t in topics:
        t["covered"] = t["topic_key"] in covered
    return jsonify({
        "topics": topics,
        "course_type": exam_map.get("course_type", "mixed"),
        "course_name": exam_map.get("course_name") or "",
        "generated_at": exam_map.get("generated_at") or "",
    })


@app.route("/api/teach")
def api_teach():
    state_dir = Path(request.args["state"])
    query = request.args.get("topic") or None
    exam_map = sa.load_exam_map(state_dir)
    course_type = exam_map.get("course_type", "mixed")
    topic, err = _safe_find_topic(exam_map, query)
    if err:
        return jsonify({"error": err}), 404
    payload = _build_teach_payload(topic, course_type)
    progress = sa.load_progress(state_dir)
    progress.setdefault("covered_topics", {})[topic["topic_key"]] = {
        "topic": topic["topic"],
        "last_covered_at": sa.now_iso(),
        "score": topic["score"],
    }
    sa.save_progress(state_dir, progress)
    return jsonify(payload)


@app.route("/api/quiz")
def api_quiz():
    state_dir = Path(request.args["state"])
    count = int(request.args.get("count", 6))
    exam_map = sa.load_exam_map(state_dir)
    course_type = exam_map.get("course_type", "mixed")
    topics = exam_map.get("topics", [])
    top = [t for t in topics if t["priority"] == "very likely exam material"][:count] or topics[:count]
    return jsonify({"questions": sa.make_quiz_questions(top, course_type, count=count), "course_type": course_type})


@app.route("/api/quiz/score", methods=["POST"])
def api_quiz_score():
    body = request.json or {}
    raw = sa.score_answer(body.get("answer", ""), body.get("expected_terms", []))
    pct = round(raw * 100)
    feedback = ("Good — you hit the key terms." if pct >= 70
                else "Partial — review the core ideas and try again." if pct >= 40
                else "Missed — re-read the sources and teach yourself this topic.")
    return jsonify({"score": raw, "pct": pct, "feedback": feedback})


@app.route("/api/plan")
def api_plan():
    state_dir = Path(request.args["state"])
    hours = float(request.args.get("hours", 2))
    exam_map = sa.load_exam_map(state_dir)
    return jsonify({"plan": sa.make_study_plan(exam_map, hours)})


@app.route("/api/review")
def api_review():
    state_dir = Path(request.args["state"])
    limit = int(request.args.get("limit", 12))
    exam_map = sa.load_exam_map(state_dir)
    return jsonify({
        "review": sa.make_review_sheet(exam_map, limit),
        "strategy": sa.make_strategy_insights_text(exam_map, state_dir),
    })


@app.route("/api/tutor/session")
def api_tutor_session():
    state_dir  = Path(request.args["state"])
    query      = request.args.get("topic") or None
    exam_map   = sa.load_exam_map(state_dir)
    course_type = exam_map.get("course_type", "mixed")

    topic, err = _safe_find_topic(exam_map, query)
    if err:
        return jsonify({"error": err}), 404

    key_sentences = sa.extract_key_sentences(topic)
    formulas      = sa.formula_lines(topic)

    # ── explanation block ──────────────────────────────────────
    name = topic["topic"]
    src_file = topic["sources"][0]["file"].replace(".pdf","").replace("_"," ") if topic.get("sources") else ""
    if course_type == "quantitative":
        plain = (
            f"{name} is something you calculate, interpret, and apply to scenarios. "
            f"{'The core relationship is: ' + formulas[0] + ' — ' if formulas else ''}"
            f"{'One anchor from your materials: ' + key_sentences[0] if key_sentences else topic.get('rationale','')}"
        )
        exam_hint = (
            "On the exam expect to: (1) extract the right values from a word problem, "
            "(2) apply the formula or method, (3) interpret the result — don't just compute, explain what it means."
        )
    else:
        plain = (
            f"{name} is a concept you need to define precisely, connect to course evidence, and apply to new cases. "
            f"{'One anchor from your materials: ' + key_sentences[0] if key_sentences else topic.get('rationale','')}"
        )
        exam_hint = (
            "On the exam expect to: (1) give a precise definition in your own words, "
            "(2) cite or describe a course-specific example, (3) explain the significance or comparison."
        )

    explanation = {
        "plain":     plain[:400],
        "exam_hint": exam_hint,
        "formulas":  formulas[:2],
        "source":    src_file,
    }

    # ── problems (different seeds so all three differ) ─────────
    def _prob(seed):
        p = sa.make_practice_problem(topic, course_type, seed)
        p["expected_terms"] = sa.expected_terms(topic)
        return p

    worked   = _prob(11)   # shown in full (step 2)
    guided   = _prob(23)   # answer hidden until submitted (step 3)
    exam_p   = _prob(47)   # harder, answer hidden (step 5)
    followup = _prob(61)   # only shown if step-3 score < 40%

    # mark covered
    progress = sa.load_progress(state_dir)
    progress.setdefault("covered_topics", {})[topic["topic_key"]] = {
        "topic": topic["topic"], "last_covered_at": sa.now_iso(), "score": topic["score"],
    }
    sa.save_progress(state_dir, progress)

    return jsonify({
        "topic":        topic["topic"],
        "topic_key":    topic["topic_key"],
        "priority":     topic["priority"],
        "score":        topic["score"],
        "confidence":   topic["confidence"],
        "course_type":  course_type,
        "explanation":  explanation,
        "worked":       worked,
        "guided":       guided,
        "exam_problem": exam_p,
        "followup":     followup,
        "sources":      topic["sources"][:3],
    })


@app.route("/api/tutor/answer", methods=["POST"])
def api_tutor_answer():
    body = request.json or {}
    raw  = sa.score_answer(body.get("answer", ""), body.get("expected_terms", []))
    pct  = round(raw * 100)
    if pct >= 70:
        level, msg = "good",    "Correct — you hit the key ideas."
    elif pct >= 40:
        level, msg = "partial", "Partial — you got some of it. Review the steps below."
    else:
        level, msg = "miss",    "Not quite — work through the solution below, then try the follow-up."
    return jsonify({"pct": pct, "level": level, "message": msg})


@app.route("/api/reviews", methods=["POST"])
def api_reviews():
    body = request.json or {}
    state_dir = Path(body["state_dir"])
    try:
        syllabus = sa.load_syllabus_analysis(state_dir, sa.load_index(state_dir))
        insights = sa.fetch_polyratings_insights(syllabus, state_dir)
        status   = insights.get("status", "unknown")
        match    = insights.get("professor_match")
        return jsonify({
            "ok": True,
            "status": status,
            "instructor": insights.get("instructor"),
            "professor_match": match.get("name") if match else None,
            "department": match.get("department") if match else None,
            "review_count": insights.get("total_review_count", 0),
            "message": _reviews_message(status, insights),
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


def _reviews_message(status: str, insights: dict) -> str:
    if status == "found":
        match = insights.get("professor_match") or {}
        dept  = match.get("department", "")
        name  = match.get("name", insights.get("instructor", ""))
        n     = insights.get("total_review_count", 0)
        note  = f" (dept: {dept})" if dept else ""
        return f"Matched {name}{note} · {n} review{'s' if n!=1 else ''} imported."
    if status == "no_professor_match":
        name = insights.get('instructor', 'unknown instructor')
        return f"No Polyratings match for \"{name}\". Rankings use syllabus/material evidence only."
    if status == "no_instructor_from_syllabus":
        return "No instructor name found in the syllabus. Add one and re-index to enable review lookup."
    if status == "error":
        return "Polyratings lookup failed (network error or API unavailable)."
    return status


@app.route("/api/progress")
def api_progress():
    state_dir = Path(request.args["state"])
    progress = sa.load_progress(state_dir)
    weak = progress.get("weak_topics", {})
    sorted_weak = sorted(weak.items(), key=lambda x: x[1].get("avg_score", 1.0))
    return jsonify({
        "covered_count": len(progress.get("covered_topics", {})),
        "quiz_count": len(progress.get("quiz_history", [])),
        "weakest": [{"key": k, **v} for k, v in sorted_weak[:5]],
    })


# ---------------------------------------------------------------------------
# routes — practice
# ---------------------------------------------------------------------------

@app.route("/api/practice/generate", methods=["POST"])
def api_practice_generate():
    body = request.json or {}
    state_dir = Path(body["state_dir"])
    kind = body.get("kind", "exam")            # "exam" | "topic"
    topic_query = body.get("topic_query") or None
    problems_per_topic = int(body.get("problems_per_topic", 2))
    variation = int(body.get("variation", 0))  # seed offset for "generate more"

    exam_map = sa.load_exam_map(state_dir)
    course_name = exam_map.get("course_name") or state_dir.name.upper().replace("-", " ")

    if kind == "exam":
        title = f"{course_name} — Practice Exam"
        ps_kind = "practice exam"
        max_topics = 5
    else:
        label = topic_query or "Top Topics"
        title = f"Problem Set: {label}"
        ps_kind = "topic-specific problem set"
        max_topics = 1

    # Build practice set; vary seed so "generate again" gives different problems
    topics = sa.choose_practice_topics(exam_map, topic_query, top=8, max_topics=max_topics)
    problems: list[dict[str, Any]] = []
    serial = 1
    for t_idx, topic in enumerate(topics, start=1):
        for local_idx in range(problems_per_topic):
            seed = (t_idx * 10 + local_idx + variation * 37) % 97
            p = sa.make_practice_problem(topic, exam_map.get("course_type", "mixed"), seed)
            p["number"] = serial
            p["source_priority"] = topic["priority"]
            p["source_score"] = topic["score"]
            p["source_confidence"] = topic["confidence"]
            p["sources"] = topic.get("sources", [])[:3]
            # Flag low-confidence problems
            low_conf = (
                topic["confidence"] in {"low", "very low"}
                or not topic.get("sources")
                or len(topic.get("sources", [])) < 2
            )
            p["low_confidence"] = low_conf
            problems.append(p)
            serial += 1

    practice_set: dict[str, Any] = {
        "title": title,
        "kind": ps_kind,
        "course_type": exam_map.get("course_type", "mixed"),
        "course_name": course_name,
        "topics": topics,
        "problems": problems,
        "created_at": sa.now_iso(),
        "variation": variation,
    }

    # Persist
    set_id = sa.slugify(title) + "--" + sa.now_iso()[:10] + (f"-v{variation}" if variation else "")
    sa.write_json(_practice_dir(state_dir) / f"{set_id}.json", practice_set)
    practice_set["id"] = set_id

    return jsonify(practice_set)


@app.route("/api/practice/list")
def api_practice_list():
    state_dir = Path(request.args["state"])
    pd = state_dir / "practice_sets"
    sets = []
    if pd.exists():
        for f in sorted(pd.glob("*.json"), reverse=True)[:20]:
            d = sa.read_json(f, {})
            if d:
                sets.append({
                    "id": f.stem,
                    "title": d.get("title", f.stem),
                    "kind": d.get("kind", ""),
                    "created_at": d.get("created_at", ""),
                    "problem_count": len(d.get("problems", [])),
                    "course_type": d.get("course_type", ""),
                })
    return jsonify(sets)


@app.route("/api/practice/export/html")
def api_practice_export_html():
    state_dir = Path(request.args["state"])
    set_id = request.args["id"]
    kind = request.args.get("kind", "worksheet")  # "worksheet" | "answer_key"

    practice_set = sa.read_json(_practice_dir(state_dir) / f"{set_id}.json", {})
    if not practice_set:
        return "Practice set not found", 404

    html_out = sa.render_answer_key_html(practice_set) if kind == "answer_key" else sa.render_worksheet_html(practice_set)
    return html_out, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/api/practice/export/pdf")
def api_practice_export_pdf():
    state_dir = Path(request.args["state"])
    set_id = request.args["id"]
    kind = request.args.get("kind", "worksheet")

    practice_set = sa.read_json(_practice_dir(state_dir) / f"{set_id}.json", {})
    if not practice_set:
        return "Practice set not found", 404

    answer_key = kind == "answer_key"
    suffix = "answer_key" if answer_key else "worksheet"
    fname = f"{sa.slugify(practice_set.get('title', 'practice'))}_{suffix}.pdf"

    tmp = Path(tempfile.mktemp(suffix=".pdf"))
    sa.write_simple_pdf(tmp, sa.practice_set_to_pdf_lines(practice_set, answer_key=answer_key))
    return send_file(tmp, as_attachment=True, download_name=fname, mimetype="application/pdf")


# ---------------------------------------------------------------------------
# launch
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    def _open():
        webbrowser.open(f"http://localhost:{PORT}")

    threading.Timer(1.2, _open).start()
    print(f"\n  Canvas Study Agent  →  http://localhost:{PORT}\n")
    app.run(debug=False, port=PORT, use_reloader=False)
