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
    raw_topics = exam_map.get("topics", [])

    # v4: Apply topic normalization — filter out OCR junk, remap canonical names.
    # Pass more candidates than needed so we have a full kept list after filtering.
    kept, demoted, rejected, _ = sa.filter_practice_topics(raw_topics[:max(limit * 2, 50)])

    # Build the display list: kept topics (canonicalized names), then demoted if needed
    display_topics: list[dict] = []
    seen_keys: set[str] = set()
    for t in kept + demoted:
        tk = t.get("topic_key", "")
        if tk not in seen_keys:
            seen_keys.add(tk)
            display_topics.append(t)
        if len(display_topics) >= limit:
            break

    progress = sa.load_progress(state_dir)
    covered = set(progress.get("covered_topics", {}).keys())
    for t in display_topics:
        t["covered"] = t["topic_key"] in covered

    return jsonify({
        "topics": display_topics,
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


def _rebuild_topic_scores_in_state(state_dir: Path) -> None:
    """Load exam_map + review_insights, re-score, overwrite exam_map.json."""
    exam_map = sa.load_exam_map(state_dir)
    review_insights = sa.load_review_insights(state_dir)
    updated = sa.rebuild_topic_scores(exam_map, review_insights)
    sa.write_json(state_dir / "exam_map.json", updated)


def _load_syllabus_meta(state_dir: Path) -> dict:
    """Load syllabus_analysis, returning {} on failure."""
    try:
        idx = sa.load_index(state_dir)
        return sa.load_syllabus_analysis(state_dir, idx)
    except Exception:
        return {}


@app.route("/api/reviews/status")
def api_reviews_status():
    """Return cached polyratings_signals for a course without triggering a fetch."""
    state_dir = Path(request.args["state"])
    data = sa.read_json(state_dir / "polyratings_signals.json", {})
    if not data:
        return jsonify({"status": "no_cache"})
    return jsonify({
        "status": data.get("status", "unknown"),
        "skip_reason": data.get("skip_reason"),
        "injection_summary": data.get("injection_summary"),
        "used_polyratings_signals": bool(
            data.get("confidence", {}).get("sufficient") and data.get("status") == "found"
        ),
        "polyratings_confidence": {"overall": (data.get("confidence") or {}).get("overall")},
    })


@app.route("/api/reviews", methods=["POST"])
def api_reviews():
    body = request.json or {}
    state_dir = Path(body["state_dir"])
    force = bool(body.get("force", False))
    try:
        # Load syllabus metadata for the gate check
        syllabus = _load_syllabus_meta(state_dir)
        professor  = syllabus.get("instructor") or body.get("professor")
        course_code = syllabus.get("course_code") or body.get("course_code")
        course_name = syllabus.get("course_name") or body.get("course_name")

        # If force=True (manual ↻), always do a full Polyratings fetch first
        if force:
            try:
                insights = sa.fetch_polyratings_insights(syllabus, state_dir)
            except Exception as exc:
                insights = {"status": "error", "error": str(exc)}
        else:
            insights = sa.load_review_insights(state_dir)

        status = insights.get("status", "unknown")

        # Rebuild topic scores if reviews found
        topics_updated = False
        if status == "found":
            try:
                _rebuild_topic_scores_in_state(state_dir)
                topics_updated = True
            except Exception:
                pass

        # Derive/refresh the structured signals cache
        signals_data = sa.ensure_reviews_cached(
            state_dir,
            professor=professor,
            course_code=course_code,
            course_name=course_name,
            force=force,
        )

        match = insights.get("professor_match")
        categories = insights.get("categories", {})
        strategy_tips = insights.get("strategy_modifiers", {}).get("teaching_style", [])
        difficult_topics = [item["insight"] for item in categories.get("difficult_topics", [])[:1]]
        exam_patterns = [item["insight"] for item in categories.get("exam_patterns", [])[:3]]
        study_strategies = [item["insight"] for item in categories.get("study_strategies", [])[:3]]

        confidence = signals_data.get("confidence") or {}

        return jsonify({
            "ok": True,
            "status": status,
            "instructor": insights.get("instructor"),
            "professor_match": match.get("name") if match else None,
            "department": match.get("department") if match else None,
            "review_count": insights.get("total_review_count", 0),
            "message": _reviews_message(status, insights),
            "strategy_tips": strategy_tips[:4],
            "exam_patterns": exam_patterns,
            "study_strategies": study_strategies,
            "difficult_topics": difficult_topics,
            "topics_updated": topics_updated,
            # v4 additions
            "injection_summary": signals_data.get("injection_summary"),
            "used_polyratings_signals": bool(confidence.get("sufficient") and status == "found"),
            "polyratings_confidence": {"overall": confidence.get("overall")},
            "signals_status": signals_data.get("status"),
            "skip_reason": signals_data.get("skip_reason"),
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
    debug_mode = bool(body.get("debug", False))

    exam_map = sa.load_exam_map(state_dir)
    course_name = exam_map.get("course_name") or state_dir.name.upper().replace("-", " ")
    course_type = exam_map.get("course_type", "mixed")

    # ── v4: Ensure Polyratings signals are cached (no-op if stale or skipped) ──
    syllabus = _load_syllabus_meta(state_dir)
    signals_data = sa.ensure_reviews_cached(
        state_dir,
        professor=syllabus.get("instructor"),
        course_code=syllabus.get("course_code"),
        course_name=syllabus.get("course_name") or course_name,
    )
    archetype_weights  = signals_data.get("archetype_weights") or {str(i): 1.0 for i in range(10)}
    signals_confidence = signals_data.get("confidence") or {}
    signals_content    = signals_data.get("signals") or {}
    poly_status        = signals_data.get("status", "no_cache")
    used_signals       = bool(signals_confidence.get("sufficient") and poly_status == "found")

    if kind == "exam":
        title = f"{course_name} — Practice Exam"
        ps_kind = "practice exam"
        max_topics = 5
    else:
        label = topic_query or "Top Topics"
        title = f"Problem Set: {label}"
        ps_kind = "topic-specific problem set"
        max_topics = 1

    # topic selection — filter_practice_topics is applied inside choose_practice_topics
    topics = sa.choose_practice_topics(exam_map, topic_query, top=8, max_topics=max_topics)

    # Collect filter debug info from a second pass (non-destructive — topics already chosen)
    _, _, _, filter_debug = sa.filter_practice_topics(
        exam_map.get("topics", [])[:max(8, max_topics)]
    )

    # Archetype sequences — ordered easy → hard to produce a difficulty curve.
    EXAM_ARCHETYPES  = [0, 3, 1, 5, 2, 4, 6, 1, 7, 2]  # multi-topic exam
    TOPIC_ARCHETYPES = [0, 3, 2, 6, 1, 5, 7, 4]         # single-topic deep dive

    archetype_seq = EXAM_ARCHETYPES if kind == "exam" else TOPIC_ARCHETYPES
    archetype_seq = (
        archetype_seq[variation % len(archetype_seq):]
        + archetype_seq[: variation % len(archetype_seq)]
    )

    # ── v4: Apply Polyratings weights + diversity floor to archetype schedule ──
    n_questions = len(topics) * problems_per_topic
    # Infer course family for recall_min calculation
    course_family, _ = sa.infer_course_family(
        syllabus.get("course_name") or course_name,
        syllabus.get("course_code") or "",
    )
    recall_min = sa.compute_recall_minimum(
        n_questions,
        family=course_family,
        signals=signals_content,
        confidence=signals_confidence,
    )
    archetype_seq = sa.apply_archetype_weights_with_floor(
        archetype_seq,
        archetype_weights,
        n_questions,
        recall_min=recall_min,
    )

    peer_names = [t["topic"] for t in topics]

    # Archetype name map for debug output
    _arch_names = {
        0: "Define-in-Context",    1: "Compute-and-Interpret", 2: "Diagnose-Flaw",
        3: "Apply-Procedure",      4: "Interpret-Output",      5: "Compare-Contrast",
        6: "What-If",              7: "Synthesize",            8: "Design-or-Evaluate",
        9: "Choose-Tool",
    }

    problems: list[dict[str, Any]] = []
    debug_questions: list[dict[str, Any]] = []
    seen_sigs: dict[str, int] = {}
    serial = 1

    for t_idx, topic in enumerate(topics, start=1):
        for local_idx in range(problems_per_topic):
            base_seed = (t_idx * 10 + local_idx + variation * 37) % 97
            problem_idx = serial - 1
            assigned_archetype = archetype_seq[problem_idx % len(archetype_seq)]

            # Structural deduplication: try up to 4 archetype rotations
            dedup_warning: str = ""
            p: dict[str, Any] = {}
            for retry in range(4):
                candidate_arch = archetype_seq[
                    (problem_idx + retry) % len(archetype_seq)
                ]
                candidate_seed = (base_seed + retry) % 97
                p = sa.make_practice_problem(
                    topic, course_type, candidate_seed,
                    archetype=candidate_arch, peers=peer_names,
                    course_name=course_name,
                )
                sig = p.get("structure_signature", "unknown")
                max_rep = sa.MAX_SIGNATURE_REPEATS.get(
                    sig, sa.MAX_SIGNATURE_REPEATS["default"]
                )
                if seen_sigs.get(sig, 0) < max_rep:
                    if retry > 0:
                        dedup_warning = (
                            f"rotated archetype {assigned_archetype}→{candidate_arch} "
                            f"(sig '{sig}' already at limit)"
                        )
                    break
            else:
                # All retries exhausted — use last candidate anyway
                dedup_warning = f"dedup limit reached, used '{sig}' anyway"

            sig = p.get("structure_signature", "unknown")
            seen_sigs[sig] = seen_sigs.get(sig, 0) + 1

            p["number"] = serial
            p["source_priority"] = topic["priority"]
            p["source_score"] = topic["score"]
            p["source_confidence"] = topic["confidence"]
            p["sources"] = topic.get("sources", [])[:3]
            # Tag each problem with its reasoning family
            arch = p.get("archetype", assigned_archetype)
            p["reasoning_family"] = sa.ARCHETYPE_TO_REASONING_FAMILY.get(arch, "RF-D")
            if dedup_warning:
                p["dedup_warning"] = dedup_warning
            low_conf = (
                topic["confidence"] in {"low", "very low"}
                or not topic.get("sources")
                or len(topic.get("sources", [])) < 2
            )
            p["low_confidence"] = low_conf
            problems.append(p)

            if debug_mode:
                debug_questions.append({
                    "number": serial,
                    "topic": topic["topic"],
                    "archetype": arch,
                    "archetype_name": _arch_names.get(arch, "specialized"),
                    "reasoning_family": p["reasoning_family"],
                    "generator": p.get("generator", "unknown"),
                    "structure_signature": sig,
                    "dedup_warning": dedup_warning or None,
                })

            serial += 1

    # ── v4: Reasoning-family diversity audit ──────────────────────────────────
    problems, audit_info = sa.run_reasoning_family_audit(problems, n_questions)

    # ── v4: Transparency fields ───────────────────────────────────────────────
    poly_confidence_out = {"overall": signals_confidence.get("overall")}

    practice_set: dict[str, Any] = {
        "title": title,
        "kind": ps_kind,
        "course_type": course_type,
        "course_name": course_name,
        "topics": topics,
        "problems": problems,
        "created_at": sa.now_iso(),
        "variation": variation,
        # v4 transparency (always present)
        "polyratings_status": poly_status,
        "used_polyratings_signals": used_signals,
        "polyratings_confidence": poly_confidence_out,
    }
    if debug_mode:
        debug_arch_weights: dict[str, Any] = {}
        if used_signals:
            debug_arch_weights = archetype_weights
        practice_set["debug"] = {
            "normalized_topics": filter_debug,
            "questions": debug_questions,
            "duplication_warnings": [
                q for q in debug_questions if q.get("dedup_warning")
            ],
            # v4 debug additions
            "polyratings_confidence": {
                "overall": signals_confidence.get("overall"),
                "review_count_score": signals_confidence.get("review_count_score"),
                "match_quality": signals_confidence.get("match_quality"),
                "review_recency": signals_confidence.get("review_recency"),
                "signal_consistency": signals_confidence.get("signal_consistency"),
                "sufficient": signals_confidence.get("sufficient"),
            },
            "archetype_weights_applied": debug_arch_weights,
            "reasoning_family_audit": audit_info,
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
