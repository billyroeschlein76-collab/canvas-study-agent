#!/usr/bin/env python3
"""
Canvas Exam Study Agent

Indexes local Canvas course files, predicts likely exam topics, and runs concise
teaching / quiz / review sessions from the indexed evidence.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


VERSION = "0.1.0"
DEFAULT_STATE = Path("state/default_course")
DEFAULT_COURSE = Path("canvas_files")
DEFAULT_SORT_COURSES = ["ECON 404", "ECON 440", "ECON 470", "BUS 321"]
DEFAULT_COURSE_ALIASES = {
    "BUS 321": [
        "Intermediate Accounting 1",
        "Intermediate Accounting I",
        "Intermediate Accounting One",
    ],
}
MAX_TOPIC_SOURCES = 8
POLYRATINGS_API_BASE = "https://api-prod.polyratings.org"


SUPPORTED_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".json",
    ".html",
    ".htm",
    ".docx",
    ".pptx",
    ".xlsx",
    ".pdf",
}


ROLE_WEIGHTS = {
    "practice_exam": 6.0,
    "exam_review": 5.5,
    "study_guide": 4.8,
    "quiz": 4.2,
    "assignment": 3.3,
    "syllabus": 2.8,
    "lecture_slides": 2.4,
    "lecture_notes": 2.2,
    "reading": 1.6,
    "discussion": 1.4,
    "unknown": 1.0,
}


SIGNAL_PATTERNS = {
    "learning_objective": re.compile(
        r"\b(learning objectives?|objectives?|by the end|you should be able to|students will be able to|"
        r"be able to|after this (lesson|unit|module))\b",
        re.I,
    ),
    "emphasis": re.compile(
        r"\b(important|key|know this|remember|must know|critical|essential|focus on|you should understand|"
        r"make sure|high yield|testable|on the exam|for the exam|exam tip|do not forget)\b",
        re.I,
    ),
    "summary": re.compile(r"\b(summary|recap|takeaways?|key points?|review|in conclusion|to summarize)\b", re.I),
    "example_problem": re.compile(
        r"\b(example|worked example|practice problem|problem set|homework|exercise|case study|sample question|"
        r"practice exam|past exam)\b",
        re.I,
    ),
    "assessment": re.compile(r"\b(quiz|exam|midterm|final|test|assignment|homework|essay prompt|short answer)\b", re.I),
    "formula": re.compile(
        r"(=|≈|≤|≥|\b(calculate|compute|derive|solve|formula|equation|function|rate|ratio|probability|"
        r"variance|regression|matrix|integral|derivative)\b)",
        re.I,
    ),
}


STOPWORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "also",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "between",
    "both",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "me",
    "more",
    "most",
    "my",
    "no",
    "nor",
    "not",
    "now",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "will",
    "with",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


GENERIC_TERMS = {
    "assignment",
    "canvas",
    "chapter",
    "class",
    "course",
    "discussion",
    "exam",
    "example",
    "final",
    "breakdown",
    "grading",
    "guide",
    "guidance",
    "homework",
    "important",
    "instructor",
    "know",
    "introduction",
    "lecture",
    "lesson",
    "material",
    "midterm",
    "module",
    "notes",
    "objective",
    "objectives",
    "page",
    "participation",
    "practice",
    "problem",
    "question",
    "quiz",
    "reading",
    "review",
    "section",
    "slide",
    "slides",
    "study",
    "summary",
    "test",
    "topic",
    "unit",
    "week",
    "worksheet",
    "able",
    "calculate",
    "classify",
    "compute",
    "connect",
    "describe",
    "explain",
    "identify",
    "learn",
    "learning",
    "student",
    "students",
    "understand",
    "using",
}


QUANT_TERMS = {
    "calculate",
    "compute",
    "derive",
    "equation",
    "formula",
    "function",
    "graph",
    "matrix",
    "model",
    "probability",
    "prove",
    "rate",
    "ratio",
    "regression",
    "solve",
    "variance",
}


READING_TERMS = {
    "argument",
    "author",
    "case",
    "claim",
    "compare",
    "contrast",
    "define",
    "essay",
    "evidence",
    "interpret",
    "reading",
    "theme",
    "thesis",
}


REVIEW_THEME_PATTERNS = [
    {
        "key": "lecture_focus",
        "label": "Students report that lectures, notes, or slides are important for exams.",
        "categories": ["study_strategies", "exam_patterns"],
        "pattern": re.compile(r"\b(lecture|lectures|class notes|notes|slides|in class|class material)\b", re.I),
        "boost_roles": ["lecture_slides", "lecture_notes"],
        "teaching_style": "anchor lessons in lecture notes and slide evidence",
    },
    {
        "key": "homework_focus",
        "label": "Students report that homework, assignments, or problem sets are important preparation.",
        "categories": ["study_strategies", "exam_patterns"],
        "pattern": re.compile(r"\b(homework|hw|assignment|assignments|problem set|problem sets|practice problems?)\b", re.I),
        "boost_roles": ["assignment"],
        "teaching_style": "use more worked examples and problem practice",
    },
    {
        "key": "quiz_focus",
        "label": "Students mention quizzes as a meaningful signal for what to study.",
        "categories": ["study_strategies", "exam_patterns"],
        "pattern": re.compile(r"\b(quiz|quizzes|pop quiz|weekly quiz)\b", re.I),
        "boost_roles": ["quiz"],
        "teaching_style": "quiz frequently with short active-recall checks",
    },
    {
        "key": "review_guide_focus",
        "label": "Students report that review sheets, study guides, or practice exams are useful.",
        "categories": ["study_strategies", "exam_patterns"],
        "pattern": re.compile(r"\b(study guide|review sheet|practice exam|practice test|sample exam|old exam|past exam|review guide)\b", re.I),
        "boost_roles": ["practice_exam", "exam_review", "study_guide"],
        "teaching_style": "prioritize review-guide and practice-exam style questions",
    },
    {
        "key": "reading_focus",
        "label": "Students report that readings or the textbook matter.",
        "categories": ["study_strategies", "exam_patterns"],
        "pattern": re.compile(r"\b(reading|readings|textbook|book|chapter|chapters)\b", re.I),
        "boost_roles": ["reading"],
        "teaching_style": "connect definitions to reading themes and examples",
    },
    {
        "key": "tricky_questions",
        "label": "Students warn that questions can be tricky, specific, or easy to misread.",
        "categories": ["exam_patterns", "pitfalls"],
        "pattern": re.compile(r"\b(tricky|specific|detail|details|wording|multiple choice|mcq|conceptual|curveball)\b", re.I),
        "boost_roles": [],
        "teaching_style": "include trap-spotting questions and explain wrong-answer patterns",
    },
    {
        "key": "cumulative_exam",
        "label": "Students mention cumulative exams or finals.",
        "categories": ["exam_patterns", "time_management"],
        "pattern": re.compile(r"\b(cumulative|comprehensive|final covers|final exam|midterm|midterms)\b", re.I),
        "boost_roles": ["exam_review", "study_guide", "practice_exam"],
        "teaching_style": "schedule mixed review across earlier units",
    },
    {
        "key": "time_load",
        "label": "Students mention time load, pacing, or starting early.",
        "categories": ["time_management", "pitfalls"],
        "pattern": re.compile(r"\b(start early|keep up|fall behind|time consuming|lots of work|workload|busy|hours|weekly)\b", re.I),
        "boost_roles": [],
        "teaching_style": "use short daily review blocks instead of one long pass",
    },
    {
        "key": "office_hours",
        "label": "Students recommend office hours or asking questions.",
        "categories": ["study_strategies"],
        "pattern": re.compile(r"\b(office hours|ask questions|go to office|email|helpful)\b", re.I),
        "boost_roles": [],
        "teaching_style": "surface confusion early and ask targeted follow-up questions",
    },
    {
        "key": "strict_grading",
        "label": "Students mention strict grading, rubrics, or point deductions.",
        "categories": ["pitfalls", "time_management"],
        "pattern": re.compile(r"\b(strict|harsh|deduct|points off|rubric|grading|graded)\b", re.I),
        "boost_roles": [],
        "teaching_style": "teach answer format and common point-loss traps",
    },
    {
        "key": "difficult_material",
        "label": "Students describe the class or material as difficult or confusing.",
        "categories": ["difficult_topics", "pitfalls"],
        "pattern": re.compile(r"\b(hard|difficult|confusing|tough|challenging|struggle|struggled)\b", re.I),
        "boost_roles": [],
        "teaching_style": "slow down on weak concepts and use more examples",
    },
]


@dataclass
class Chunk:
    id: str
    file_path: str
    file_name: str
    file_role: str
    section: str
    chunk_index: int
    text: str
    word_count: int
    signals: dict[str, int]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str, default: str = "item") -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return value or default


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def clean_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def safe_relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


class HTMLTextExtractor:
    def __init__(self) -> None:
        from html.parser import HTMLParser

        class Parser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.parts: list[str] = []

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                if tag.lower() in {"p", "br", "li", "h1", "h2", "h3", "h4", "tr", "div"}:
                    self.parts.append("\n")

            def handle_data(self, data: str) -> None:
                if data.strip():
                    self.parts.append(data)

            def text(self) -> str:
                return html.unescape(" ".join(self.parts))

        self.Parser = Parser

    def extract(self, text: str) -> str:
        parser = self.Parser()
        parser.feed(text)
        return clean_whitespace(parser.text())


def extract_plain_text(path: Path) -> str:
    return clean_whitespace(path.read_text(encoding="utf-8", errors="ignore"))


def extract_delimited(path: Path, delimiter: str) -> str:
    rows: list[str] = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for row in reader:
            rows.append(" | ".join(cell.strip() for cell in row if cell.strip()))
    return clean_whitespace("\n".join(rows))


def extract_json(path: Path) -> str:
    data = read_json(path, {})
    return clean_whitespace(json.dumps(data, indent=2, ensure_ascii=False))


def xml_text(element: ET.Element) -> str:
    parts: list[str] = []
    for node in element.iter():
        if node.tag.endswith("}t") or node.tag.endswith("}v"):
            if node.text:
                parts.append(node.text)
    return " ".join(parts)


def extract_docx(path: Path) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        names = [name for name in zf.namelist() if name == "word/document.xml" or name.startswith("word/header")]
        for name in names:
            root = ET.fromstring(zf.read(name))
            for para in root.iter():
                if para.tag.endswith("}p"):
                    text = xml_text(para).strip()
                    if text:
                        parts.append(text)
    return clean_whitespace("\n".join(parts))


def slide_sort_key(name: str) -> tuple[int, str]:
    match = re.search(r"slide(\d+)\.xml$", name)
    return (int(match.group(1)) if match else 0, name)


def extract_pptx(path: Path) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        names = sorted(
            [name for name in zf.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")],
            key=slide_sort_key,
        )
        for idx, name in enumerate(names, start=1):
            root = ET.fromstring(zf.read(name))
            text = xml_text(root).strip()
            if text:
                parts.append(f"Slide {idx}\n{text}")
    return clean_whitespace("\n\n".join(parts))


def extract_xlsx(path: Path) -> str:
    parts: list[str] = []
    shared: list[str] = []
    with zipfile.ZipFile(path) as zf:
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for item in root:
                shared.append(xml_text(item))
        sheet_names = sorted(name for name in zf.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", name))
        for sheet_idx, name in enumerate(sheet_names, start=1):
            root = ET.fromstring(zf.read(name))
            rows: list[str] = []
            for row in root.iter():
                if not row.tag.endswith("}row"):
                    continue
                cells: list[str] = []
                for cell in row:
                    if not cell.tag.endswith("}c"):
                        continue
                    cell_type = cell.attrib.get("t")
                    value = ""
                    for child in cell:
                        if child.tag.endswith("}v") and child.text:
                            value = child.text
                            break
                    if cell_type == "s" and value.isdigit() and int(value) < len(shared):
                        value = shared[int(value)]
                    if value.strip():
                        cells.append(value.strip())
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                parts.append(f"Sheet {sheet_idx}\n" + "\n".join(rows))
    return clean_whitespace("\n\n".join(parts))


def extract_pdf(path: Path) -> tuple[str, str | None]:
    try:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(str(path))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        return clean_whitespace(text), None
    except Exception:
        pass

    try:
        import PyPDF2  # type: ignore

        reader = PyPDF2.PdfReader(str(path))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        return clean_whitespace(text), None
    except Exception:
        pass

    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        result = subprocess.run(
            [pdftotext, "-layout", str(path), "-"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            return clean_whitespace(result.stdout), None
        return "", result.stderr.strip() or "pdftotext could not extract this PDF"

    return "", "PDF extraction needs pypdf/PyPDF2 or the pdftotext command installed"


def extract_file(path: Path) -> tuple[str, str | None]:
    suffix = path.suffix.lower()
    try:
        if suffix in {".txt", ".md", ".markdown"}:
            return extract_plain_text(path), None
        if suffix == ".csv":
            return extract_delimited(path, ","), None
        if suffix == ".tsv":
            return extract_delimited(path, "\t"), None
        if suffix == ".json":
            return extract_json(path), None
        if suffix in {".html", ".htm"}:
            return HTMLTextExtractor().extract(extract_plain_text(path)), None
        if suffix == ".docx":
            return extract_docx(path), None
        if suffix == ".pptx":
            return extract_pptx(path), None
        if suffix == ".xlsx":
            return extract_xlsx(path), None
        if suffix == ".pdf":
            return extract_pdf(path)
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"
    return "", f"Unsupported file type: {suffix}"


def parse_course_codes(values: list[str] | None) -> list[str]:
    if not values:
        return DEFAULT_SORT_COURSES
    joined = " ".join(values)
    matches = re.findall(r"\b[A-Z]{2,6}\s*[- ]?\s*\d{3}[A-Z]?\b", joined.upper())
    if matches:
        return list(dict.fromkeys(normalize_course_code(match) for match in matches if normalize_course_code(match)))
    courses: list[str] = []
    for value in values:
        for part in re.split(r"[,;]", value):
            code = normalize_course_code(part)
            if code:
                courses.append(code)
    return list(dict.fromkeys(courses)) or DEFAULT_SORT_COURSES


def course_match_count(text: str, course: str) -> int:
    code = normalize_course_code(course)
    if not code:
        return 0
    dept, number = code.split()
    pattern = re.compile(rf"\b{re.escape(dept)}\s*[-_ ]?\s*{re.escape(number)}\b", re.I)
    matches = len(pattern.findall(text))
    for alias in DEFAULT_COURSE_ALIASES.get(code, []):
        alias_pattern = alias_to_pattern(alias)
        matches += len(alias_pattern.findall(text))
    return matches


def alias_to_pattern(alias: str) -> re.Pattern[str]:
    tokens = [re.escape(token) for token in re.findall(r"[A-Za-z0-9]+", alias)]
    normalized_tokens: list[str] = []
    for token in tokens:
        if token.lower() in {"1", "i", "one"}:
            normalized_tokens.append(r"(?:1|i|one)")
        else:
            normalized_tokens.append(token)
    return re.compile(r"\b" + r"[\s_\-]+".join(normalized_tokens) + r"\b", re.I)


def infer_course_for_file(path: Path, source_root: Path, courses: list[str], scan_content: bool = True) -> tuple[str | None, dict[str, Any]]:
    rel_text = safe_relpath(path, source_root)
    name_text = f"{rel_text} {path.name}"
    scores = Counter()
    reasons: dict[str, list[str]] = defaultdict(list)

    for course in courses:
        name_hits = course_match_count(name_text, course)
        if name_hits:
            scores[course] += name_hits * 4
            reasons[course].append("filename/path")

    extraction_warning = None
    if scan_content and path.suffix.lower() in SUPPORTED_EXTENSIONS:
        text, extraction_warning = extract_file(path)
        sample = text[:12000]
        for course in courses:
            content_hits = course_match_count(sample, course)
            if content_hits:
                scores[course] += content_hits * 2
                reasons[course].append("file content")

    if not scores:
        return None, {"scores": {}, "reason": "no course-code match", "warning": extraction_warning}

    ranked = scores.most_common()
    best_course, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if best_score < 2 or (second_score and best_score < second_score + 2):
        return None, {
            "scores": dict(scores),
            "reason": "ambiguous course-code match",
            "warning": extraction_warning,
        }
    return best_course, {
        "scores": dict(scores),
        "reason": ", ".join(dict.fromkeys(reasons[best_course])),
        "warning": extraction_warning,
    }


def unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def should_skip_sort_path(path: Path, source_root: Path, dest_root: Path) -> bool:
    parts = set(path.parts)
    if "__pycache__" in parts or ".git" in parts:
        return True
    if any(part.endswith((".app", ".framework", ".bundle", ".plugin")) for part in path.parts):
        return True
    try:
        path.relative_to(dest_root)
        return True
    except ValueError:
        pass
    try:
        relative = path.relative_to(source_root)
        if relative.parts and relative.parts[0] in {"state", "prompts", "docs", "examples"}:
            return True
    except ValueError:
        pass
    return False


def sort_canvas_files(
    source_dir: Path,
    dest_root: Path,
    courses: list[str],
    scan_content: bool = True,
    move: bool = False,
    dry_run: bool = False,
    include_unmatched: bool = False,
) -> dict[str, Any]:
    source_dir = source_dir.expanduser().resolve()
    dest_root = dest_root.expanduser().resolve()
    if not source_dir.exists():
        raise SystemExit(f"Source folder does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise SystemExit(f"Source must be a folder: {source_dir}")

    results: dict[str, Any] = {
        "source": str(source_dir),
        "destination": str(dest_root),
        "courses": courses,
        "mode": "move" if move else "copy",
        "dry_run": dry_run,
        "sorted": [],
        "unmatched": [],
        "warnings": [],
    }

    for course in courses:
        if not dry_run:
            (dest_root / course).mkdir(parents=True, exist_ok=True)
    unmatched_dir = dest_root / "_unsorted"
    if include_unmatched and not dry_run:
        unmatched_dir.mkdir(parents=True, exist_ok=True)

    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if should_skip_sort_path(path.resolve(), source_dir, dest_root):
            continue

        course, meta = infer_course_for_file(path, source_dir, courses, scan_content)
        if meta.get("warning"):
            results["warnings"].append({"file": safe_relpath(path, source_dir), "warning": meta["warning"]})
        if course:
            target_dir = dest_root / course
            target = unique_destination(target_dir / path.name)
            action = "move" if move else "copy"
            if not dry_run:
                target_dir.mkdir(parents=True, exist_ok=True)
                if move:
                    shutil.move(str(path), str(target))
                else:
                    shutil.copy2(path, target)
            results["sorted"].append(
                {
                    "file": safe_relpath(path, source_dir),
                    "course": course,
                    "target": safe_relpath(target, Path.cwd()),
                    "action": action,
                    "reason": meta["reason"],
                    "scores": meta["scores"],
                }
            )
        else:
            record = {"file": safe_relpath(path, source_dir), "reason": meta["reason"], "scores": meta["scores"]}
            if include_unmatched:
                target = unique_destination(unmatched_dir / path.name)
                if not dry_run:
                    if move:
                        shutil.move(str(path), str(target))
                    else:
                        shutil.copy2(path, target)
                record["target"] = safe_relpath(target, Path.cwd())
                record["action"] = "move" if move else "copy"
            results["unmatched"].append(record)
    return results


def infer_file_role(path: Path) -> str:
    name = " ".join(path.parts).lower()
    compact = re.sub(r"[_\-]+", " ", name)
    if re.search(r"\b(practice|past|sample)\s+(exam|midterm|final|test)\b", compact):
        return "practice_exam"
    if re.search(r"\b(exam|midterm|final|test)\s+(review|study guide|prep|outline)\b", compact):
        return "exam_review"
    if re.search(r"\b(review sheet|review guide|exam review|final review|midterm review)\b", compact):
        return "exam_review"
    if re.search(r"\b(study guide|studyguide)\b", compact):
        return "study_guide"
    if re.search(r"\bquiz|quizzes\b", compact):
        return "quiz"
    if re.search(r"\b(homework|assignment|problem set|worksheet|lab|project)\b", compact):
        return "assignment"
    if re.search(r"\bsyllabus\b", compact):
        return "syllabus"
    if re.search(r"\b(slides?|deck|powerpoint|ppt)\b", compact) or path.suffix.lower() == ".pptx":
        return "lecture_slides"
    if re.search(r"\b(lecture|notes?|outline)\b", compact):
        return "lecture_notes"
    if re.search(r"\b(reading|article|chapter|textbook)\b", compact):
        return "reading"
    if re.search(r"\b(discussion|forum|seminar)\b", compact):
        return "discussion"
    return "unknown"


def is_heading(line: str) -> bool:
    clean = line.strip()
    if not clean or len(clean) > 120:
        return False
    if clean.startswith("#"):
        return True
    words = clean.split()
    if len(words) > 12:
        return False
    if clean.endswith(":") and len(words) <= 10:
        return True
    letters = re.sub(r"[^A-Za-z]", "", clean)
    if len(letters) >= 4 and letters.isupper():
        return True
    titleish = sum(1 for word in words if word[:1].isupper())
    if len(words) >= 2 and titleish / max(len(words), 1) >= 0.7 and not clean.endswith("."):
        return True
    if re.match(r"^(unit|module|week|chapter|lesson|section)\s+\d+[:.\-\s]", clean, re.I):
        return True
    return False


def detect_signals(text: str) -> dict[str, int]:
    signals: dict[str, int] = {}
    for name, pattern in SIGNAL_PATTERNS.items():
        signals[name] = len(pattern.findall(text))
    signals["heading"] = sum(1 for line in text.splitlines() if is_heading(line))
    signals["question"] = text.count("?")
    return signals


def chunk_text(
    text: str,
    path: Path,
    role: str,
    root: Path,
    max_words: int = 650,
    overlap_words: int = 80,
    min_words: int | None = None,
) -> list[Chunk]:
    lines = [line.strip() for line in text.splitlines()]
    chunks: list[Chunk] = []
    current_lines: list[str] = []
    current_heading = "General"
    chunk_index = 0
    minimum_words = 3 if role == "syllabus" else (min_words or 15)

    def flush(keep_overlap: bool = True) -> None:
        nonlocal current_lines, chunk_index
        chunk_text_value = clean_whitespace("\n".join(current_lines))
        words = re.findall(r"\b[\w'-]+\b", chunk_text_value)
        if len(words) < minimum_words:
            current_lines = []
            return
        chunk_id = f"{slugify(path.stem)}-{chunk_index:04d}"
        chunks.append(
            Chunk(
                id=chunk_id,
                file_path=safe_relpath(path, root),
                file_name=path.name,
                file_role=role,
                section=current_heading,
                chunk_index=chunk_index,
                text=chunk_text_value,
                word_count=len(words),
                signals=detect_signals(chunk_text_value),
            )
        )
        chunk_index += 1
        if keep_overlap and overlap_words > 0:
            overlap = " ".join(words[-overlap_words:])
            current_lines = [overlap] if overlap else []
        else:
            current_lines = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            current_lines.append("")
            continue
        if is_heading(line):
            if current_lines:
                flush(keep_overlap=False)
            current_heading = re.sub(r"^#+\s*", "", line).rstrip(":").strip() or current_heading
        current_lines.append(line)
        if len(" ".join(current_lines).split()) >= max_words:
            flush()

    if current_lines:
        flush()
    return chunks


def iter_course_files(course_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in course_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            if any(part.startswith(".") for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text)]


def clean_phrase(phrase: str) -> str:
    phrase = re.sub(r"[^A-Za-z0-9' /+\-]", " ", phrase.lower())
    phrase = re.sub(r"\s+", " ", phrase).strip()
    words = phrase.split()
    while words and (words[0].isdigit() or words[0] in STOPWORDS or words[0] in GENERIC_TERMS):
        words.pop(0)
    while words and (words[-1].isdigit() or words[-1] in STOPWORDS or words[-1] in GENERIC_TERMS):
        words.pop()
    if len(words) > 6:
        words = words[:6]
    return " ".join(words)


def normalize_topic(phrase: str) -> str:
    words = clean_phrase(phrase).split()
    normalized: list[str] = []
    for word in words:
        if len(word) > 4 and word.endswith("s") and not word.endswith(("ss", "us", "is", "es")):
            word = word[:-1]
        normalized.append(word)
    return " ".join(normalized)


def useful_phrase(phrase: str) -> bool:
    words = phrase.split()
    if not words or len(words) > 6:
        return False
    if all(word in STOPWORDS or word in GENERIC_TERMS for word in words):
        return False
    if len(words) >= 4 and len(set(words)) / len(words) <= 0.75:
        return False
    if sum(len(word) >= 4 and word not in GENERIC_TERMS for word in words) == 0:
        return False
    if re.fullmatch(r"\d+(\s+\d+)*", phrase):
        return False
    return True


def extract_topic_candidates(chunk: dict[str, Any]) -> Counter[str]:
    text = chunk["text"]
    counter: Counter[str] = Counter()

    for line in text.splitlines():
        clean = line.strip(" -\t*•")
        if is_heading(clean):
            if chunk.get("file_role") == "syllabus" and is_syllabus_admin_heading(clean):
                continue
            for phrase in heading_phrases(clean):
                if useful_phrase(phrase):
                    counter[phrase] += 10
        elif SIGNAL_PATTERNS["learning_objective"].search(clean) or SIGNAL_PATTERNS["emphasis"].search(clean):
            for phrase in sentence_phrases(clean, max_ngram=4):
                counter[phrase] += 3

    if chunk.get("file_role") == "syllabus" and is_syllabus_admin_only_section(chunk.get("section", "")):
        return counter

    all_phrases = sentence_phrases(text, max_ngram=3)
    for phrase, count in all_phrases.items():
        counter[phrase] += min(count, 4)
    return counter


def is_syllabus_admin_heading(line: str) -> bool:
    if normalize_course_code(line):
        return True
    return bool(
        re.search(
            r"\b(syllabus|instructor|professor|grading|breakdown|participation|office|contact|email|policy|policies|"
            r"schedule|calendar|attendance|late work|academic integrity|learning objectives?|exam guidance)\b",
            line,
            re.I,
        )
    )


def is_syllabus_admin_only_section(section: str) -> bool:
    if normalize_course_code(section):
        return True
    return bool(
        re.search(
            r"\b(instructor|professor|grading|breakdown|participation|office|contact|email|policy|policies|"
            r"schedule|calendar|attendance|late work|academic integrity)\b",
            section,
            re.I,
        )
    )


def heading_phrases(line: str) -> list[str]:
    clean = re.sub(r"^#+\s*", "", line).strip()
    clean = re.sub(r"^(unit|module|week|chapter|lesson|section)\s+\d+[\s:.\-]*", "", clean, flags=re.I)
    pieces = [clean]
    if ":" in clean:
        pieces.insert(0, clean.split(":")[-1])
    phrases: list[str] = []
    for piece in pieces:
        piece = re.sub(r"\b(review|overview|introduction|summary|recap|slides?|notes?)\b", " ", piece, flags=re.I)
        phrase = normalize_topic(piece)
        if useful_phrase(phrase):
            phrases.append(phrase)
    return list(dict.fromkeys(phrases))


def sentence_phrases(text: str, max_ngram: int = 3) -> Counter[str]:
    counter: Counter[str] = Counter()
    sentences = re.split(r"[\n.;:!?]+", text)
    for sentence in sentences:
        tokens = [
            token
            for token in tokenize(sentence)
            if token not in STOPWORDS and token not in GENERIC_TERMS and len(token) >= 3
        ]
        if not tokens:
            continue
        for n in range(1, min(max_ngram, 4) + 1):
            if len(tokens) < n:
                continue
            for idx in range(0, len(tokens) - n + 1):
                phrase = normalize_topic(" ".join(tokens[idx : idx + n]))
                if useful_phrase(phrase):
                    counter[phrase] += 1
    return counter


def snippet_for_topic(text: str, topic: str, width: int = 260) -> str:
    normalized = text.lower()
    idx = normalized.find(topic.lower())
    if idx < 0:
        words = text.split()
        return clean_whitespace(" ".join(words[:45]))[:width]
    start = max(0, idx - width // 2)
    end = min(len(text), idx + width // 2)
    snippet = text[start:end]
    snippet = re.sub(r"^\S*\s", "", snippet)
    snippet = re.sub(r"\s\S*$", "", snippet)
    return clean_whitespace(snippet)


def signal_multiplier(signals: dict[str, int]) -> float:
    value = 1.0
    value += min(signals.get("learning_objective", 0), 3) * 0.50
    value += min(signals.get("emphasis", 0), 4) * 0.45
    value += min(signals.get("summary", 0), 3) * 0.30
    value += min(signals.get("example_problem", 0), 4) * 0.35
    value += min(signals.get("assessment", 0), 4) * 0.35
    value += min(signals.get("heading", 0), 4) * 0.25
    value += min(signals.get("formula", 0), 4) * 0.20
    return value


def phrase_quality(phrase: str) -> float:
    words = phrase.split()
    if len(words) == 1:
        return 0.40
    if len(words) == 2:
        return 1.15
    if len(words) == 3:
        return 1.25
    if len(words) == 4:
        return 1.20
    return 1.00


def detect_course_type(chunks: list[dict[str, Any]]) -> str:
    sample = " ".join(chunk["text"][:1000] for chunk in chunks[:100])
    tokens = tokenize(sample)
    formula_signal_count = sum(chunk.get("signals", {}).get("formula", 0) for chunk in chunks[:100])
    quant_count = sum(1 for token in tokens if token in QUANT_TERMS) + sample.count("=") * 2 + formula_signal_count * 3
    reading_count = sum(1 for token in tokens if token in READING_TERMS)
    if quant_count >= max(8, reading_count * 1.25):
        return "quantitative"
    if reading_count >= max(10, quant_count * 1.1):
        return "reading-heavy"
    return "mixed"


def normalize_course_code(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"\b([A-Z]{2,6})\s*[- ]?\s*(\d{3}[A-Z]?)\b", value.upper())
    if not match:
        return None
    return f"{match.group(1)} {match.group(2)}"


def split_sentences(text: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [clean_whitespace(piece) for piece in pieces if len(clean_whitespace(piece).split()) >= 4]


def line_context(lines: list[str], idx: int, radius: int = 2) -> str:
    start = max(0, idx - radius)
    end = min(len(lines), idx + radius + 1)
    return clean_whitespace(" ".join(lines[start:end]))


def clean_instructor_name(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"\b(professor|prof\.?|instructor|teacher|lecturer|dr\.?|ph\.?d\.?|office|email)\b", " ", value, flags=re.I)
    value = re.sub(r"[:|;,].*$", " ", value)
    value = re.sub(r"\S+@\S+", " ", value)
    value = re.sub(r"[^A-Za-z .'-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value.split()) < 2:
        return None
    return value


def extract_instructor(lines: list[str]) -> str | None:
    patterns = [
        re.compile(r"\b(?:professor|prof\.?|instructor|lecturer|teacher|dr\.?)\s*[:\-]?\s*([A-Z][A-Za-z .'-]{2,80})", re.I),
        re.compile(r"\b([A-Z][A-Za-z .'-]{2,80})\s*[,|-]\s*(?:professor|instructor|lecturer)\b", re.I),
    ]
    for line in lines[:120]:
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                name = clean_instructor_name(match.group(1))
                if name:
                    return name
    return None


def extract_course_identity(lines: list[str]) -> tuple[str | None, str | None]:
    course_code = None
    course_name = None
    for line in lines[:80]:
        code = normalize_course_code(line)
        if code and not course_code:
            course_code = code
            remainder = re.sub(re.escape(code.replace(" ", "")), "", line, flags=re.I)
            remainder = re.sub(r"\b" + re.escape(code) + r"\b", "", remainder, flags=re.I)
            remainder = re.sub(r"\b(syllabus|course)\b", " ", remainder, flags=re.I)
            remainder = re.sub(r"[:|,\-–—]+", " ", remainder)
            remainder = clean_whitespace(remainder).strip("# ")
            if 2 <= len(remainder.split()) <= 12:
                course_name = remainder
        if course_code and course_name:
            break
    if not course_name:
        for line in lines[:20]:
            clean = line.strip("# ").strip()
            if 2 <= len(clean.split()) <= 12 and not re.search(r"\b(syllabus|schedule|spring|fall|winter|summer)\b", clean, re.I):
                course_name = clean
                break
    return course_code, course_name


def collect_syllabus_lines(chunks: list[dict[str, Any]]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for chunk in chunks:
        if chunk.get("file_role") != "syllabus":
            continue
        for line in chunk.get("text", "").splitlines():
            clean = clean_whitespace(line.strip(" -\t*•"))
            if clean:
                records.append({"line": clean, "file": chunk["file_path"], "section": chunk["section"]})
    return records


def extract_percent_lines(records: list[dict[str, str]], pattern: re.Pattern[str] | None = None) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for idx, record in enumerate(records):
        line = record["line"]
        if "%" not in line and not re.search(r"\bpoints?\b", line, re.I):
            continue
        if pattern and not pattern.search(line):
            continue
        output.append({**record, "context": line_context([r["line"] for r in records], idx)})
    return output[:12]


def extract_guided_lines(records: list[dict[str, str]], pattern: re.Pattern[str], limit: int = 12) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    lines = [record["line"] for record in records]
    for idx, record in enumerate(records):
        if pattern.search(record["line"]):
            output.append({**record, "context": line_context(lines, idx)})
            if len(output) >= limit:
                break
    return output


def analyze_syllabus(index: dict[str, Any], state_dir: Path | None = None) -> dict[str, Any]:
    records = collect_syllabus_lines(index.get("chunks", []))
    analysis = {
        "status": "not_found",
        "course_code": None,
        "course_name": None,
        "instructor": None,
        "grading_breakdown": [],
        "exam_weighting": [],
        "important_topics": [],
        "learning_objectives": [],
        "exam_guidance": [],
        "sources": [],
        "created_at": now_iso(),
    }
    if not records:
        if state_dir:
            write_json(state_dir / "syllabus_analysis.json", analysis)
        return analysis

    lines = [record["line"] for record in records]
    course_code, course_name = extract_course_identity(lines)
    analysis.update(
        {
            "status": "found",
            "course_code": course_code,
            "course_name": course_name,
            "instructor": extract_instructor(lines),
            "grading_breakdown": extract_percent_lines(records),
            "exam_weighting": extract_percent_lines(records, re.compile(r"\b(exam|midterm|final|quiz|test)\b", re.I)),
            "important_topics": extract_guided_lines(
                records,
                re.compile(r"\b(important|key topics?|focus|know this|must know|essential|major topics?)\b", re.I),
            ),
            "learning_objectives": extract_guided_lines(records, SIGNAL_PATTERNS["learning_objective"]),
            "exam_guidance": extract_guided_lines(
                records,
                re.compile(r"\b(exam|midterm|final|test).*(cover|cumulative|focus|include|format|closed|open|practice|review)|"
                           r"\b(cover|cumulative|focus|format|closed|open|practice|review).*(exam|midterm|final|test)\b", re.I),
            ),
            "sources": sorted({f"{record['file']} :: {record['section']}" for record in records}),
        }
    )
    if state_dir:
        write_json(state_dir / "syllabus_analysis.json", analysis)
    return analysis


def trpc_query(path: str, input_data: dict[str, Any] | None = None, api_base: str = POLYRATINGS_API_BASE) -> Any:
    url = f"{api_base.rstrip('/')}/{path}"
    if input_data is not None:
        encoded = urllib.parse.quote(json.dumps(input_data, separators=(",", ":")))
        url = f"{url}?input={encoded}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CanvasStudyAgent/0.1",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        message = payload["error"].get("message", "Unknown Polyratings API error")
        raise RuntimeError(message)
    return payload.get("result", {}).get("data")


def professor_display_name(professor: dict[str, Any]) -> str:
    return clean_whitespace(f"{professor.get('firstName', '')} {professor.get('lastName', '')}")


def professor_match_score(professor: dict[str, Any], instructor: str, course_code: str | None) -> float:
    instructor_clean = clean_instructor_name(instructor) or instructor
    instructor_l = instructor_clean.lower()
    full_name = professor_display_name(professor).lower()
    score = difflib.SequenceMatcher(None, full_name, instructor_l).ratio()

    instructor_tokens = {token.lower().strip(".") for token in re.findall(r"[A-Za-z.]+", instructor_clean)}
    first = str(professor.get("firstName", "")).lower()
    last = str(professor.get("lastName", "")).lower()
    if last and last in instructor_tokens:
        score += 0.45
    if first and first in instructor_tokens:
        score += 0.25
    elif first and any(token and token[0] == first[0] and len(token) <= 2 for token in instructor_tokens):
        score += 0.12

    normalized_code = normalize_course_code(course_code)
    if normalized_code:
        dept = normalized_code.split()[0]
        courses = " ".join(professor.get("courses", [])).upper()
        if normalized_code in courses:
            score += 0.25
        elif professor.get("department") == dept:
            score += 0.10
    return score


def find_professor_match(professors: list[dict[str, Any]], instructor: str, course_code: str | None) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    scored = []
    for professor in professors:
        score = professor_match_score(professor, instructor, course_code)
        scored.append({"score": round(score, 3), "professor": professor})
    scored.sort(key=lambda item: item["score"], reverse=True)
    top_matches = [
        {
            "score": item["score"],
            "id": item["professor"].get("id"),
            "name": professor_display_name(item["professor"]),
            "department": item["professor"].get("department"),
            "courses": item["professor"].get("courses", []),
            "num_evals": item["professor"].get("numEvals"),
            "overall_rating": item["professor"].get("overallRating"),
        }
        for item in scored[:5]
    ]
    if not scored or scored[0]["score"] < 0.78:
        return None, top_matches
    return scored[0]["professor"], top_matches


def flatten_reviews(professor: dict[str, Any], course_code: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    course_reviews: list[dict[str, Any]] = []
    all_reviews: list[dict[str, Any]] = []
    normalized_course = normalize_course_code(course_code)
    for course_name, reviews in professor.get("reviews", {}).items():
        normalized_review_course = normalize_course_code(course_name)
        for review in reviews:
            record = {
                **review,
                "courseName": course_name,
                "normalizedCourseName": normalized_review_course,
            }
            all_reviews.append(record)
            if normalized_course and normalized_review_course == normalized_course:
                course_reviews.append(record)
    return course_reviews, all_reviews, bool(course_reviews)


def first_matching_sentence(text: str, pattern: re.Pattern[str]) -> str:
    for sentence in split_sentences(text):
        if pattern.search(sentence):
            return sentence
    return clean_whitespace(text)[:240]


def reliability_label(support_count: int, total_reviews: int) -> str:
    if support_count >= 3 or (support_count >= 2 and total_reviews <= 5):
        return "recurring student-reported pattern"
    if support_count == 2:
        return "limited student-reported pattern"
    return "isolated student report"


def review_reliability_weight(reliability: str) -> float:
    if reliability.startswith("recurring"):
        return 1.0
    if reliability.startswith("limited"):
        return 0.55
    return 0.2


def analyze_polyratings_reviews(
    professor: dict[str, Any],
    course_reviews: list[dict[str, Any]],
    all_reviews: list[dict[str, Any]],
    course_specific_used: bool,
) -> dict[str, Any]:
    scoped_reviews = course_reviews if course_specific_used else all_reviews
    categories: dict[str, list[dict[str, Any]]] = {
        "study_strategies": [],
        "exam_patterns": [],
        "difficult_topics": [],
        "time_management": [],
        "pitfalls": [],
        "recurring_themes": [],
    }
    role_boosts: Counter[str] = Counter()
    teaching_style: Counter[str] = Counter()

    for theme in REVIEW_THEME_PATTERNS:
        matches = []
        review_ids = set()
        for review in scoped_reviews:
            text = str(review.get("rating", ""))
            if not theme["pattern"].search(text):
                continue
            review_id = str(review.get("id", f"{review.get('courseName', '')}-{len(matches)}"))
            review_ids.add(review_id)
            matches.append(
                {
                    "course": review.get("courseName"),
                    "post_date": review.get("postDate"),
                    "example": first_matching_sentence(text, theme["pattern"]),
                }
            )
        support_count = len(review_ids)
        if support_count == 0:
            continue
        reliability = reliability_label(support_count, len(scoped_reviews))
        insight = {
            "insight": theme["label"],
            "support_count": support_count,
            "review_count": len(scoped_reviews),
            "reliability": reliability,
            "source": "student-reported",
            "examples": matches[:3],
        }
        for category in theme["categories"]:
            categories[category].append(insight)
        categories["recurring_themes"].append(insight)
        if review_reliability_weight(reliability) >= 0.55:
            for role in theme["boost_roles"]:
                role_boosts[role] += review_reliability_weight(reliability)
            teaching_style[theme["teaching_style"]] += support_count

    difficult_topic_terms = extract_difficult_topic_terms(scoped_reviews)
    if difficult_topic_terms:
        categories["difficult_topics"].insert(
            0,
            {
                "insight": "Review text repeatedly names these possible difficult-topic cues: "
                + ", ".join(term for term, _ in difficult_topic_terms[:6]),
                "support_count": sum(count for _, count in difficult_topic_terms[:6]),
                "review_count": len(scoped_reviews),
                "reliability": "student-reported keyword pattern",
                "source": "student-reported",
                "examples": [],
            },
        )

    role_boost_dict = {role: round(1.0 + min(0.18, count * 0.06), 3) for role, count in role_boosts.items()}
    strategy_modifiers = {
        "role_boosts": role_boost_dict,
        "teaching_style": [style for style, _ in teaching_style.most_common(5)],
        "review_scope": "course-specific reviews" if course_specific_used else "professor-wide reviews",
    }
    return {
        "categories": categories,
        "strategy_modifiers": strategy_modifiers,
        "review_scope": strategy_modifiers["review_scope"],
    }


def extract_difficult_topic_terms(reviews: list[dict[str, Any]]) -> list[tuple[str, int]]:
    difficulty_pattern = re.compile(r"\b(hard|difficult|confusing|tough|challenging|struggle|struggled)\b", re.I)
    counter: Counter[str] = Counter()
    for review in reviews:
        text = str(review.get("rating", ""))
        for sentence in split_sentences(text):
            if not difficulty_pattern.search(sentence):
                continue
            for phrase, count in sentence_phrases(sentence, max_ngram=2).items():
                if useful_phrase(phrase):
                    counter[phrase] += count
    return counter.most_common(8)


def fetch_polyratings_insights(
    syllabus_analysis: dict[str, Any],
    state_dir: Path,
    api_base: str = POLYRATINGS_API_BASE,
) -> dict[str, Any]:
    course_code = syllabus_analysis.get("course_code")
    instructor = syllabus_analysis.get("instructor")
    base = {
        "created_at": now_iso(),
        "source": "polyratings.dev",
        "api_base": api_base,
        "course_code": course_code,
        "course_name": syllabus_analysis.get("course_name"),
        "instructor": instructor,
        "status": "not_run",
        "professor_match": None,
        "top_matches": [],
        "course_review_count": 0,
        "total_review_count": 0,
        "course_specific_used": False,
        "review_url": None,
        "categories": {
            "study_strategies": [],
            "exam_patterns": [],
            "difficult_topics": [],
            "time_management": [],
            "pitfalls": [],
            "recurring_themes": [],
        },
        "strategy_modifiers": {"role_boosts": {}, "teaching_style": [], "review_scope": "none"},
    }

    if not instructor:
        base["status"] = "no_instructor_from_syllabus"
        write_json(state_dir / "review_insights.json", base)
        return base

    try:
        professors = trpc_query("professors.all", api_base=api_base)
        professor, top_matches = find_professor_match(professors, instructor, course_code)
        base["top_matches"] = top_matches
        if not professor:
            base["status"] = "no_professor_match"
            write_json(state_dir / "review_insights.json", base)
            return base

        full_professor = trpc_query("professors.get", {"id": professor["id"]}, api_base=api_base)
        course_reviews, all_reviews, course_specific_used = flatten_reviews(full_professor, course_code)
        base["professor_match"] = {
            "id": full_professor.get("id"),
            "name": professor_display_name(full_professor),
            "department": full_professor.get("department"),
            "num_evals": full_professor.get("numEvals"),
            "overall_rating": full_professor.get("overallRating"),
            "material_clear": full_professor.get("materialClear"),
            "student_difficulties": full_professor.get("studentDifficulties"),
        }
        base["review_url"] = f"https://polyratings.dev/professor/{full_professor.get('id')}"
        base["course_review_count"] = len(course_reviews)
        base["total_review_count"] = len(all_reviews)
        base["course_specific_used"] = course_specific_used
        if not all_reviews:
            base["status"] = "no_reviews_found"
            write_json(state_dir / "review_insights.json", base)
            return base

        analyzed = analyze_polyratings_reviews(full_professor, course_reviews, all_reviews, course_specific_used)
        base.update(analyzed)
        base["status"] = "found"
        write_json(state_dir / "review_insights.json", base)
        return base
    except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        base["status"] = "fetch_failed"
        base["error"] = f"{type(exc).__name__}: {exc}"
        write_json(state_dir / "review_insights.json", base)
        return base


def make_index(course_dir: Path, state_dir: Path) -> dict[str, Any]:
    course_dir = course_dir.resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    files = iter_course_files(course_dir)
    chunks: list[Chunk] = []
    file_records: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []

    for file_path in files:
        role = infer_file_role(file_path.relative_to(course_dir))
        text, warning = extract_file(file_path)
        if warning:
            warnings.append({"file": safe_relpath(file_path, course_dir), "warning": warning})
        word_count = len(re.findall(r"\b[\w'-]+\b", text))
        record = {
            "path": safe_relpath(file_path, course_dir),
            "name": file_path.name,
            "extension": file_path.suffix.lower(),
            "role": role,
            "word_count": word_count,
        }
        file_records.append(record)
        if word_count >= 15:
            chunks.extend(chunk_text(text, file_path, role, course_dir))

    chunk_dicts = [asdict(chunk) for chunk in chunks]
    index = {
        "version": VERSION,
        "created_at": now_iso(),
        "course_dir": str(course_dir),
        "file_count": len(files),
        "chunk_count": len(chunks),
        "course_type": detect_course_type(chunk_dicts),
        "files": file_records,
        "chunks": chunk_dicts,
        "warnings": warnings,
    }
    index["syllabus_analysis"] = analyze_syllabus(index, state_dir)
    write_json(state_dir / "course_index.json", index)
    return index


def source_signal_summary(signals: dict[str, int]) -> list[str]:
    labels = []
    for key in ["learning_objective", "emphasis", "summary", "example_problem", "assessment", "heading", "formula"]:
        if signals.get(key, 0):
            labels.append(key.replace("_", " "))
    return labels


def load_syllabus_analysis(state_dir: Path, index: dict[str, Any] | None = None) -> dict[str, Any]:
    if index and index.get("syllabus_analysis"):
        return index["syllabus_analysis"]
    return read_json(state_dir / "syllabus_analysis.json", {"status": "not_found"})


def load_review_insights(state_dir: Path) -> dict[str, Any]:
    return read_json(
        state_dir / "review_insights.json",
        {
            "status": "not_run",
            "categories": {
                "study_strategies": [],
                "exam_patterns": [],
                "difficult_topics": [],
                "time_management": [],
                "pitfalls": [],
                "recurring_themes": [],
            },
            "strategy_modifiers": {"role_boosts": {}, "teaching_style": [], "review_scope": "none"},
        },
    )


def apply_review_adjustments(stats: dict[str, dict[str, Any]], review_insights: dict[str, Any]) -> None:
    if review_insights.get("status") != "found":
        for item in stats.values():
            item["review_adjustments"] = []
        return

    role_boosts = review_insights.get("strategy_modifiers", {}).get("role_boosts", {})
    review_topic_terms = review_topic_keywords(review_insights)
    for item in stats.values():
        factor = 1.0
        adjustments: list[str] = []
        for role in item["roles"]:
            boost = float(role_boosts.get(role, 1.0))
            if boost > 1.0:
                factor *= boost
                adjustments.append(f"boosted because student reviews emphasize {role.replace('_', ' ')}")
        topic_words = significant_word_set(item["topic"])
        if topic_words and review_topic_terms and topic_words.intersection(review_topic_terms):
            factor *= 1.08
            adjustments.append("boosted because related terms appear in student-reported review themes")
        item["score"] *= min(factor, 1.30)
        item["review_adjustments"] = adjustments[:3]


def review_topic_keywords(review_insights: dict[str, Any]) -> set[str]:
    text_parts: list[str] = []
    for category_items in review_insights.get("categories", {}).values():
        for item in category_items:
            if review_reliability_weight(item.get("reliability", "")) < 0.55:
                continue
            text_parts.append(str(item.get("insight", "")))
            for example in item.get("examples", []):
                text_parts.append(str(example.get("example", "")))
    terms = {
        token
        for token in tokenize(" ".join(text_parts))
        if token not in STOPWORDS and token not in GENERIC_TERMS and len(token) >= 4
    }
    return terms


def build_exam_map(index: dict[str, Any], state_dir: Path) -> dict[str, Any]:
    stats: dict[str, dict[str, Any]] = {}

    for chunk in index["chunks"]:
        candidates = extract_topic_candidates(chunk)
        role_weight = ROLE_WEIGHTS.get(chunk["file_role"], 1.0)
        mult = signal_multiplier(chunk["signals"])

        for phrase, count in candidates.items():
            topic = normalize_topic(phrase)
            if not useful_phrase(topic):
                continue
            item = stats.setdefault(
                topic,
                {
                    "topic": topic,
                    "raw_score": 0.0,
                    "occurrences": 0,
                    "files": set(),
                    "roles": Counter(),
                    "signals": Counter(),
                    "sources": [],
                    "source_keys": set(),
                },
            )
            contribution = count * role_weight * mult * phrase_quality(topic)
            item["raw_score"] += contribution
            item["occurrences"] += count
            item["files"].add(chunk["file_path"])
            item["roles"][chunk["file_role"]] += 1
            item["signals"].update({k: v for k, v in chunk["signals"].items() if v})
            source_key = (chunk["file_path"], chunk["section"])
            if len(item["sources"]) < MAX_TOPIC_SOURCES and source_key not in item["source_keys"]:
                item["source_keys"].add(source_key)
                item["sources"].append(
                    {
                        "file": chunk["file_path"],
                        "section": chunk["section"],
                        "role": chunk["file_role"],
                        "signals": source_signal_summary(chunk["signals"]),
                        "snippet": snippet_for_topic(chunk["text"], topic),
                    }
                )

    if not stats:
        exam_map = {
            "version": VERSION,
            "created_at": now_iso(),
            "course_type": index.get("course_type", "mixed"),
            "topics": [],
        }
        write_json(state_dir / "exam_map.json", exam_map)
        return exam_map

    for item in stats.values():
        file_count = len(item["files"])
        repeat_bonus = 1.0 + min(1.4, math.log1p(file_count) / 1.2)
        assessment_bonus = 1.0
        if item["roles"].get("practice_exam"):
            assessment_bonus += 0.75
        if item["roles"].get("exam_review") or item["roles"].get("study_guide"):
            assessment_bonus += 0.55
        if item["roles"].get("quiz") or item["roles"].get("assignment"):
            assessment_bonus += 0.30
        item["score"] = item["raw_score"] * repeat_bonus * assessment_bonus

    stats = merge_same_concept_topics(stats)
    stats = prune_redundant_topics(stats)
    review_insights = load_review_insights(state_dir)
    apply_review_adjustments(stats, review_insights)
    top_score = max(item["score"] for item in stats.values())
    topics: list[dict[str, Any]] = []
    for item in stats.values():
        normalized_score = round((item["score"] / top_score) * 100, 1)
        file_count = len(item["files"])
        roles = sorted(item["roles"].keys())
        signals = dict(item["signals"].most_common())

        if normalized_score >= 65 and (
            file_count >= 2
            or any(role in item["roles"] for role in ["practice_exam", "exam_review", "study_guide", "quiz"])
        ):
            priority = "very likely exam material"
        elif normalized_score >= 30:
            priority = "possibly testable material"
        else:
            priority = "low-priority material"

        confidence_points = 0
        confidence_points += min(file_count, 3)
        confidence_points += 2 if any(role in item["roles"] for role in ["practice_exam", "exam_review", "study_guide"]) else 0
        confidence_points += 1 if item["signals"].get("learning_objective") else 0
        confidence_points += 1 if item["signals"].get("emphasis") else 0
        confidence = "high" if confidence_points >= 5 else "medium" if confidence_points >= 3 else "low"

        rationale = make_rationale(item, normalized_score, confidence)
        topics.append(
            {
                "topic": title_topic(item["topic"]),
                "topic_key": item["topic"],
                "score": normalized_score,
                "priority": priority,
                "confidence": confidence,
                "rationale": rationale,
                "occurrences": item["occurrences"],
                "file_count": file_count,
                "roles": roles,
                "signals": signals,
                "sources": item["sources"],
                "review_adjustments": item.get("review_adjustments", []),
            }
        )

    topics.sort(key=lambda x: x["score"], reverse=True)
    exam_map = {
        "version": VERSION,
        "created_at": now_iso(),
        "course_type": index.get("course_type", "mixed"),
        "topic_count": len(topics),
        "topics": topics,
        "syllabus_analysis": load_syllabus_analysis(state_dir, index),
        "review_insights": review_insights,
    }
    write_json(state_dir / "exam_map.json", exam_map)
    return exam_map


def merge_same_concept_topics(stats: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    passthrough: dict[str, dict[str, Any]] = {}
    for topic, item in stats.items():
        sig = tuple(sorted(significant_word_set(topic)))
        if len(sig) >= 2:
            grouped[sig].append((topic, item))
        else:
            passthrough[topic] = item

    merged: dict[str, dict[str, Any]] = dict(passthrough)
    for group_items in grouped.values():
        if len(group_items) == 1:
            topic, item = group_items[0]
            merged[topic] = item
            continue
        canonical_topic, canonical = max(
            group_items,
            key=lambda pair: (len(pair[0].split()), pair[1]["score"], pair[1]["occurrences"]),
        )
        combined = canonical
        combined["topic"] = canonical_topic
        combined["raw_score"] = max(item["raw_score"] for _, item in group_items) + sum(
            item["raw_score"] for topic, item in group_items if topic != canonical_topic
        ) * 0.25
        combined["score"] = max(item["score"] for _, item in group_items) + sum(
            item["score"] for topic, item in group_items if topic != canonical_topic
        ) * 0.25
        combined["occurrences"] = sum(item["occurrences"] for _, item in group_items)
        combined["files"] = set().union(*(item["files"] for _, item in group_items))
        combined["roles"] = Counter()
        combined["signals"] = Counter()
        combined["sources"] = []
        combined["source_keys"] = set()
        for _, item in group_items:
            combined["roles"].update(item["roles"])
            combined["signals"].update(item["signals"])
            for source in item["sources"]:
                key = (source["file"], source["section"])
                if key not in combined["source_keys"] and len(combined["sources"]) < MAX_TOPIC_SOURCES:
                    combined["source_keys"].add(key)
                    combined["sources"].append(source)
        merged[canonical_topic] = combined
    return merged


def prune_redundant_topics(stats: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    items = list(stats.items())
    keep: dict[str, dict[str, Any]] = {}
    for topic, item in items:
        words = significant_word_set(topic)
        if not words:
            continue
        better_specific = False
        for other_topic, other in items:
            if other_topic == topic:
                continue
            other_words = significant_word_set(other_topic)
            if not other_words:
                continue
            same_concept_with_better_name = words == other_words and (
                other["score"] > item["score"] or len(other_topic.split()) > len(topic.split())
            )
            more_specific_concept = words.issubset(other_words) and len(other_words) > len(words)
            over_specific_low_value = other_words.issubset(words) and len(words) > len(other_words) and other["score"] >= item["score"] * 1.5
            if not (same_concept_with_better_name or more_specific_concept or over_specific_low_value):
                continue
            if other["score"] >= item["score"] * 0.40:
                better_specific = True
                break
        if not better_specific:
            keep[topic] = item
    return keep


def significant_word_set(topic: str) -> set[str]:
    return {word for word in topic.split() if word not in STOPWORDS and word not in GENERIC_TERMS}


def make_rationale(item: dict[str, Any], score: float, confidence: str) -> str:
    parts: list[str] = []
    if item["roles"].get("practice_exam"):
        parts.append("appears in practice/past exam material")
    if item["roles"].get("exam_review") or item["roles"].get("study_guide"):
        parts.append("appears in review or study-guide material")
    if item["roles"].get("quiz") or item["roles"].get("assignment"):
        parts.append("shows up in homework/quiz-style assessment material")
    file_count = len(item["files"])
    if file_count >= 2:
        parts.append(f"repeats across {file_count} files")
    if item["signals"].get("learning_objective"):
        parts.append("linked to learning-objective language")
    if item["signals"].get("emphasis"):
        parts.append("near instructor-emphasis phrasing")
    if item["signals"].get("example_problem"):
        parts.append("supported by examples or practice problems")
    if item.get("review_adjustments"):
        parts.append("student-reported Polyratings patterns modestly increase its priority")
    if not parts:
        parts.append("ranked from frequency and heading/context signals")
    return f"{'; '.join(parts)}. Confidence is {confidence}; normalized score {score:.1f}/100."


def title_topic(topic: str) -> str:
    small = {"and", "or", "of", "in", "to", "for", "with", "vs"}
    words = []
    for idx, word in enumerate(topic.split()):
        if idx > 0 and word in small:
            words.append(word)
        elif word.isupper():
            words.append(word)
        else:
            words.append(word.capitalize())
    return " ".join(words)


def load_index(state_dir: Path) -> dict[str, Any]:
    path = state_dir / "course_index.json"
    if not path.exists():
        raise SystemExit(f"No course index found at {path}. Run: python3 study_agent.py index --course <course-folder>")
    return read_json(path, {})


def load_exam_map(state_dir: Path) -> dict[str, Any]:
    path = state_dir / "exam_map.json"
    if not path.exists():
        index = load_index(state_dir)
        return build_exam_map(index, state_dir)
    return read_json(path, {})


def load_progress(state_dir: Path) -> dict[str, Any]:
    return read_json(
        state_dir / "progress.json",
        {
            "created_at": now_iso(),
            "covered_topics": {},
            "quiz_history": [],
            "weakness": {},
        },
    )


def save_progress(state_dir: Path, progress: dict[str, Any]) -> None:
    progress["updated_at"] = now_iso()
    write_json(state_dir / "progress.json", progress)


def print_wrapped(text: str = "", indent: int = 0, width: int = 92) -> None:
    prefix = " " * indent
    if not text:
        print()
        return
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            print()
        else:
            print(textwrap.fill(paragraph.strip(), width=width, initial_indent=prefix, subsequent_indent=prefix))


def print_topic_table(topics: list[dict[str, Any]], limit: int) -> None:
    for idx, topic in enumerate(topics[:limit], start=1):
        print(f"{idx}. {topic['topic']} [{topic['priority']}; score {topic['score']}/100; {topic['confidence']} confidence]")
        print_wrapped(topic["rationale"], indent=3)
        for source in topic["sources"][:3]:
            signal_suffix = f" ({', '.join(source['signals'])})" if source["signals"] else ""
            print(f"   - {source['file']} :: {source['section']}{signal_suffix}")
        print()


def concise_evidence_list(items: list[dict[str, Any]], key: str = "line", limit: int = 4) -> list[str]:
    output = []
    useful_items = [item for item in items if not str(item.get("line", "")).lstrip().startswith("#")]
    for item in (useful_items or items)[:limit]:
        text = item.get(key) or item.get("line") or item.get("insight") or ""
        source = item.get("file")
        section = item.get("section")
        if source and section:
            output.append(f"{text} [{source} :: {section}]")
        else:
            output.append(str(text))
    return output


def print_syllabus_summary(syllabus: dict[str, Any]) -> None:
    print("\nSyllabus Analysis:")
    if syllabus.get("status") != "found":
        print("- No syllabus file was identified. Put the syllabus in the course folder and include 'syllabus' in the filename for best results.")
        return
    print(f"- Course: {syllabus.get('course_code') or 'unknown code'} {syllabus.get('course_name') or ''}".rstrip())
    print(f"- Instructor: {syllabus.get('instructor') or 'not found'}")
    if syllabus.get("exam_weighting"):
        print("- Exam weighting:")
        for item in concise_evidence_list(syllabus["exam_weighting"], limit=5):
            print_wrapped(f"- {item}", indent=2)
    elif syllabus.get("grading_breakdown"):
        print("- Grading breakdown:")
        for item in concise_evidence_list(syllabus["grading_breakdown"], limit=5):
            print_wrapped(f"- {item}", indent=2)
    if syllabus.get("learning_objectives"):
        print("- Learning objectives / stated priorities:")
        for item in concise_evidence_list(syllabus["learning_objectives"], limit=4):
            print_wrapped(f"- {item}", indent=2)
    if syllabus.get("important_topics"):
        print("- Important topics / emphasis:")
        for item in concise_evidence_list(syllabus["important_topics"], limit=4):
            print_wrapped(f"- {item}", indent=2)
    if syllabus.get("exam_guidance"):
        print("- Exam guidance:")
        for item in concise_evidence_list(syllabus["exam_guidance"], limit=4):
            print_wrapped(f"- {item}", indent=2)


def category_lines(review_insights: dict[str, Any], category: str, limit: int = 3) -> list[str]:
    items = review_insights.get("categories", {}).get(category, [])
    items = sorted(items, key=lambda item: (review_reliability_weight(item.get("reliability", "")), item.get("support_count", 0)), reverse=True)
    lines = []
    for item in items[:limit]:
        support = item.get("support_count", 0)
        reliability = item.get("reliability", "student-reported")
        lines.append(f"{item.get('insight')} ({reliability}; {support} supporting review{'s' if support != 1 else ''})")
    return lines


def make_strategy_insights_text(exam_map_or_index: dict[str, Any], state_dir: Path | None = None) -> str:
    syllabus = exam_map_or_index.get("syllabus_analysis") or (load_syllabus_analysis(state_dir) if state_dir else {"status": "not_found"})
    review_insights = exam_map_or_index.get("review_insights") or (load_review_insights(state_dir) if state_dir else {"status": "not_run"})
    lines = ["Professor & Course Strategy Insights", ""]

    lines.append("From syllabus/materials")
    if syllabus.get("status") == "found":
        course = " ".join(part for part in [syllabus.get("course_code"), syllabus.get("course_name")] if part)
        lines.append(f"- Course: {course or 'not extracted'}")
        lines.append(f"- Instructor: {syllabus.get('instructor') or 'not extracted'}")
        if syllabus.get("exam_weighting"):
            for item in concise_evidence_list(syllabus["exam_weighting"], limit=3):
                lines.append(f"- Exam/grading signal: {item}")
        if syllabus.get("learning_objectives"):
            for item in concise_evidence_list(syllabus["learning_objectives"], limit=2):
                lines.append(f"- Objective signal: {item}")
        if syllabus.get("important_topics"):
            for item in concise_evidence_list(syllabus["important_topics"], limit=2):
                lines.append(f"- Important-topic signal: {item}")
        if syllabus.get("exam_guidance"):
            for item in concise_evidence_list(syllabus["exam_guidance"], limit=2):
                lines.append(f"- Exam guidance: {item}")
    else:
        lines.append("- No syllabus was identified, so this section is based only on indexed course materials.")

    lines.append("")
    lines.append("From student reviews (polyratings.dev)")
    status = review_insights.get("status")
    if status == "found":
        professor = review_insights.get("professor_match") or {}
        scope = "course-specific" if review_insights.get("course_specific_used") else "professor-wide"
        lines.append(
            f"- Matched professor: {professor.get('name', 'unknown')} "
            f"({review_insights.get('course_review_count', 0)} course-specific reviews, "
            f"{review_insights.get('total_review_count', 0)} total; using {scope} review patterns)."
        )
        for heading, category in [
            ("Study strategies", "study_strategies"),
            ("Exam patterns", "exam_patterns"),
            ("Difficult topics", "difficult_topics"),
            ("Time management", "time_management"),
            ("Pitfalls", "pitfalls"),
        ]:
            insights = category_lines(review_insights, category, limit=2)
            for insight in insights:
                lines.append(f"- {heading}: {insight}")
    elif status == "not_run":
        lines.append("- Review lookup has not been run. Use `python3 study_agent.py reviews --state <state-folder>` or `rank --with-reviews`.")
    elif status == "no_instructor_from_syllabus":
        lines.append("- No instructor name was extracted from the syllabus, so Polyratings lookup was skipped.")
    elif status == "no_professor_match":
        lines.append("- No reliable Polyratings professor match was found. The agent will not fabricate review insights.")
    elif status == "no_reviews_found":
        lines.append("- A professor match was found, but no reviews were available. The agent will continue from course materials only.")
    elif status == "fetch_failed":
        lines.append(f"- Review lookup failed: {review_insights.get('error', 'unknown error')}. The agent will continue from course materials only.")
    else:
        lines.append("- No review insights are available.")

    lines.append("")
    lines.append("Agent inference")
    course_type = exam_map_or_index.get("course_type", "mixed")
    lines.append(f"- Detected course type: {course_type}.")
    modifiers = review_insights.get("strategy_modifiers", {})
    role_boosts = modifiers.get("role_boosts", {})
    if role_boosts:
        readable = ", ".join(f"{role.replace('_', ' ')} x{boost}" for role, boost in role_boosts.items())
        lines.append(f"- Topic ranking is modestly adjusted toward review-supported material types: {readable}.")
    else:
        lines.append("- Topic ranking is driven by syllabus/material evidence; review-based boosts are absent or too weak.")
    teaching_styles = modifiers.get("teaching_style", [])
    if teaching_styles:
        lines.append("- Teaching style adjustment: " + "; ".join(teaching_styles[:4]) + ".")
    elif course_type == "quantitative":
        lines.append("- Teaching style adjustment: emphasize formulas, problem patterns, worked examples, and trap checks.")
    elif course_type == "reading-heavy":
        lines.append("- Teaching style adjustment: emphasize themes, definitions, arguments, comparisons, and essay prompts.")
    else:
        lines.append("- Teaching style adjustment: mix concise concept explanation with application and active recall.")
    return "\n".join(lines)


def command_index(args: argparse.Namespace) -> None:
    course_dir = Path(args.course)
    state_dir = Path(args.state)
    if not course_dir.exists():
        raise SystemExit(f"Course folder does not exist: {course_dir}")
    index = make_index(course_dir, state_dir)
    print(f"Indexed {index['file_count']} files into {index['chunk_count']} chunks.")
    print(f"Detected course type: {index['course_type']}")
    print_syllabus_summary(index.get("syllabus_analysis", {}))
    print(f"Saved: {state_dir / 'course_index.json'}")
    if index["warnings"]:
        print("\nExtraction warnings:")
        for warning in index["warnings"]:
            print(f"- {warning['file']}: {warning['warning']}")


def command_sort_files(args: argparse.Namespace) -> None:
    courses = parse_course_codes(args.courses)
    results = sort_canvas_files(
        source_dir=Path(args.source),
        dest_root=Path(args.dest),
        courses=courses,
        scan_content=not args.no_content_scan,
        move=args.move,
        dry_run=args.dry_run,
        include_unmatched=args.include_unmatched,
    )
    action = "Would move" if args.dry_run and args.move else "Would copy" if args.dry_run else "Moved" if args.move else "Copied"
    print(f"{action} {len(results['sorted'])} files into course folders.")
    if results["sorted"]:
        print("\nSorted files:")
        for item in results["sorted"]:
            print(f"- {item['file']} -> {item['course']} ({item['reason']})")
    if results["unmatched"]:
        print(f"\nUnmatched files: {len(results['unmatched'])}")
        for item in results["unmatched"][:20]:
            print(f"- {item['file']} ({item['reason']})")
        if len(results["unmatched"]) > 20:
            print(f"- ... {len(results['unmatched']) - 20} more")
    if results["warnings"]:
        print("\nExtraction warnings:")
        for warning in results["warnings"][:20]:
            print(f"- {warning['file']}: {warning['warning']}")


def command_rank(args: argparse.Namespace) -> None:
    state_dir = Path(args.state)
    index = load_index(state_dir)
    if getattr(args, "with_reviews", False):
        syllabus = load_syllabus_analysis(state_dir, index)
        print("Fetching Polyratings review insights...")
        insights = fetch_polyratings_insights(syllabus, state_dir, args.api_base)
        print(f"Review lookup status: {insights.get('status')}")
    exam_map = build_exam_map(index, state_dir)
    print(f"Exam-likelihood map built from {index['chunk_count']} chunks.")
    print(f"Detected course type: {exam_map['course_type']}")
    print()
    print_topic_table(exam_map["topics"], args.limit)
    print(make_strategy_insights_text(exam_map, state_dir))
    print()
    print(f"Saved: {state_dir / 'exam_map.json'}")


def command_reviews(args: argparse.Namespace) -> None:
    state_dir = Path(args.state)
    index = load_index(state_dir)
    syllabus = load_syllabus_analysis(state_dir, index)
    insights = fetch_polyratings_insights(syllabus, state_dir, args.api_base)
    print(make_strategy_insights_text({**index, "review_insights": insights}, state_dir))
    print(f"\nSaved: {state_dir / 'review_insights.json'}")


def command_strategy(args: argparse.Namespace) -> None:
    state_dir = Path(args.state)
    exam_map_path = state_dir / "exam_map.json"
    if exam_map_path.exists():
        data = load_exam_map(state_dir)
    else:
        data = load_index(state_dir)
    print(make_strategy_insights_text(data, state_dir))


def find_topic(exam_map: dict[str, Any], query: str | None, top: int | None = None) -> dict[str, Any]:
    topics = exam_map.get("topics", [])
    if not topics:
        raise SystemExit("No topics found. Run rank after indexing real course files.")
    if top is not None:
        idx = max(1, top) - 1
        if idx >= len(topics):
            raise SystemExit(f"Only {len(topics)} topics are available.")
        return topics[idx]
    if not query:
        return topics[0]
    q = normalize_topic(query)
    matches = []
    for topic in topics:
        haystack = " ".join(
            [
                topic["topic_key"],
                topic["topic"],
                " ".join(source["section"] for source in topic["sources"]),
                " ".join(source["file"] for source in topic["sources"]),
            ]
        ).lower()
        if q in haystack or query.lower() in haystack:
            matches.append(topic)
    if matches:
        return sorted(matches, key=lambda item: item["score"], reverse=True)[0]
    raise SystemExit(f"No matching topic found for '{query}'. Try: python3 study_agent.py rank")


def extract_key_sentences(topic: dict[str, Any], limit: int = 5) -> list[str]:
    topic_key = topic["topic_key"]
    sentences: list[str] = []
    for source in topic["sources"]:
        text = source.get("snippet", "")
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            sentence = clean_whitespace(sentence)
            if len(sentence.split()) >= 5:
                sentences.append(sentence)
    preferred = [s for s in sentences if topic_key in s.lower()]
    output = preferred + [s for s in sentences if s not in preferred]
    seen: set[str] = set()
    unique: list[str] = []
    for sentence in output:
        key = sentence.lower()
        if key not in seen:
            seen.add(key)
            unique.append(sentence)
        if len(unique) >= limit:
            break
    return unique


def likely_question_templates(topic: dict[str, Any], course_type: str) -> list[str]:
    name = topic["topic"]
    if course_type == "quantitative":
        return [
            f"Given a scenario, choose the right formula or method for {name} and solve step by step.",
            f"Explain what each term or variable means in a {name} problem.",
            f"Identify the common mistake in a worked {name} solution.",
        ]
    if course_type == "reading-heavy":
        return [
            f"Define {name} and explain why it matters in the course argument.",
            f"Compare {name} with a related concept, author, case, or theme.",
            f"Use evidence from the readings to support a short-answer or essay claim about {name}.",
        ]
    return [
        f"Define {name} in your own words and explain why it matters.",
        f"Apply {name} to a new example or scenario.",
        f"Compare {name} with a related course concept and avoid the obvious trap.",
    ]


def formula_lines(topic: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for source in topic["sources"]:
        for line in source.get("snippet", "").splitlines():
            if SIGNAL_PATTERNS["formula"].search(line):
                lines.append(clean_whitespace(line))
    return lines[:4]


def teach_topic(topic: dict[str, Any], course_type: str, state_dir: Path | None = None, mark_covered: bool = True) -> None:
    print(f"# {topic['topic']}")
    print(f"Priority: {topic['priority']} | Score: {topic['score']}/100 | Confidence: {topic['confidence']}")
    print()
    print("Why this is likely testable:")
    print_wrapped(topic["rationale"], indent=2)
    print()

    key_sentences = extract_key_sentences(topic)
    print("Simple explanation:")
    if key_sentences:
        print_wrapped(
            f"Treat {topic['topic']} as a high-yield idea you need to define, recognize in context, "
            f"and apply. The course evidence points to these anchors: {' '.join(key_sentences[:2])}",
            indent=2,
        )
    else:
        print_wrapped(
            f"Treat {topic['topic']} as a testable idea. Your job is to explain what it means, when it applies, "
            f"and what an instructor could ask you to do with it.",
            indent=2,
        )
    print()

    print("Core ideas to know:")
    core_items = key_sentences[:4] or [source["snippet"] for source in topic["sources"][:4]]
    for item in core_items:
        print_wrapped(f"- {item}", indent=2)
    if course_type == "quantitative":
        formulas = formula_lines(topic)
        if formulas:
            print_wrapped("- Formula/equation cues from the files: " + " | ".join(formulas), indent=2)
        else:
            print_wrapped("- For quantitative problems, memorize the givens, target unknown, method, and final interpretation.", indent=2)
    elif course_type == "reading-heavy":
        print_wrapped("- For reading-heavy exams, connect the definition to themes, arguments, evidence, and comparisons.", indent=2)
    print()

    print("Likely exam question styles:")
    for question in likely_question_templates(topic, course_type):
        print_wrapped(f"- {question}", indent=2)
    print()

    print("Worked example pattern:")
    if course_type == "quantitative":
        print_wrapped(
            f"1. Identify what the problem is asking about {topic['topic']}. 2. Write the known values or assumptions. "
            "3. Choose the formula or rule. 4. Substitute carefully. 5. Check units/signs and explain the result.",
            indent=2,
        )
    else:
        print_wrapped(
            f"1. State a clear definition of {topic['topic']}. 2. Add the course-specific evidence or example. "
            "3. Explain the consequence, comparison, or why the idea matters. 4. End with a direct answer to the prompt.",
            indent=2,
        )
    print()

    print("Common traps:")
    traps = [
        f"Giving a vague definition of {topic['topic']} without course-specific language.",
        "Recognizing the term but failing to apply it to a new problem, passage, or scenario.",
        "Ignoring the source context that made the topic high-priority.",
    ]
    if course_type == "quantitative":
        traps.append("Skipping units, assumptions, or the interpretation after the calculation.")
    if course_type == "reading-heavy":
        traps.append("Listing facts instead of making a comparison, argument, or evidence-backed claim.")
    for trap in traps:
        print_wrapped(f"- {trap}", indent=2)
    print()

    print("Short quiz:")
    for idx, question in enumerate(make_quiz_questions([topic], course_type, count=3), start=1):
        print_wrapped(f"{idx}. {question['question']}", indent=2)
    print()

    print("Spaced repetition prompts:")
    prompts = [
        f"Tomorrow: define {topic['topic']} without looking.",
        f"In 3 days: answer one likely exam-style question about {topic['topic']}.",
        f"In 7 days: compare {topic['topic']} with another high-yield topic from the map.",
    ]
    for prompt in prompts:
        print_wrapped(f"- {prompt}", indent=2)
    print()

    print("Evidence:")
    for source in topic["sources"][:5]:
        signal_suffix = f" ({', '.join(source['signals'])})" if source["signals"] else ""
        print_wrapped(f"- {source['file']} :: {source['section']}{signal_suffix}", indent=2)

    if state_dir:
        print()
        print(make_strategy_insights_text(load_exam_map(state_dir), state_dir))

    if state_dir and mark_covered:
        progress = load_progress(state_dir)
        progress.setdefault("covered_topics", {})[topic["topic_key"]] = {
            "topic": topic["topic"],
            "last_covered_at": now_iso(),
            "score": topic["score"],
        }
        save_progress(state_dir, progress)


def make_quiz_questions(topics: list[dict[str, Any]], course_type: str, count: int = 5) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for topic in topics:
        expected = expected_terms(topic)
        if course_type == "quantitative":
            templates = [
                f"What information would you identify first before solving a {topic['topic']} problem?",
                f"What formula, rule, or method is most associated with {topic['topic']} in the course files?",
                f"What is one common calculation or interpretation trap for {topic['topic']}?",
            ]
        elif course_type == "reading-heavy":
            templates = [
                f"Define {topic['topic']} in one or two sentences.",
                f"What evidence, author, case, or theme would you connect to {topic['topic']}?",
                f"What comparison or essay prompt could an instructor ask about {topic['topic']}?",
            ]
        else:
            templates = [
                f"Define {topic['topic']} in your own words.",
                f"How would you apply {topic['topic']} to a new example?",
                f"What is the most likely exam trap for {topic['topic']}?",
            ]
        for template in templates:
            questions.append({"topic": topic["topic"], "topic_key": topic["topic_key"], "question": template, "expected_terms": expected})
            if len(questions) >= count:
                return questions
    return questions[:count]


def expected_terms(topic: dict[str, Any], limit: int = 8) -> list[str]:
    text = " ".join(source.get("snippet", "") for source in topic["sources"])
    terms = [
        token
        for token in tokenize(text + " " + topic["topic_key"])
        if token not in STOPWORDS and token not in GENERIC_TERMS and len(token) >= 4
    ]
    return [term for term, _ in Counter(terms).most_common(limit)]


def score_answer(answer: str, expected: list[str]) -> float:
    if not answer.strip() or not expected:
        return 0.0
    answer_terms = set(tokenize(answer))
    hits = sum(1 for term in expected if term in answer_terms)
    return hits / max(3, min(len(expected), 6))


def choose_practice_topics(exam_map: dict[str, Any], topic_query: str | None, top: int, max_topics: int) -> list[dict[str, Any]]:
    if topic_query:
        return [find_topic(exam_map, topic_query)]
    topics = exam_map.get("topics", [])
    selected = [topic for topic in topics[: max(top, max_topics)] if topic["priority"] != "low-priority material"]
    if not selected:
        selected = topics[:max_topics]
    return selected[:max_topics]


def number_value(seed: int, base: int, step: int, mod: int) -> int:
    return base + (seed % mod) * step


def classify_elasticity(value: float) -> str:
    abs_value = abs(value)
    if abs_value > 1.05:
        return "elastic"
    if abs_value < 0.95:
        return "inelastic"
    return "approximately unit elastic"


def make_elasticity_problem(topic: dict[str, Any], seed: int) -> dict[str, Any]:
    p1 = number_value(seed, 8, 2, 5)
    p2 = p1 + 2
    q1 = number_value(seed, 90, 10, 5)
    q2 = q1 - number_value(seed, 12, 4, 4)
    pct_q = (q2 - q1) / ((q1 + q2) / 2)
    pct_p = (p2 - p1) / ((p1 + p2) / 2)
    elasticity = pct_q / pct_p
    tr1 = p1 * q1
    tr2 = p2 * q2
    return {
        "topic": topic["topic"],
        "prompt": (
            f"A product's price rises from ${p1} to ${p2}. Quantity demanded falls from {q1} to {q2}. "
            "Using the midpoint method, calculate price elasticity of demand, classify demand, and state what happens to total revenue."
        ),
        "answer": f"Elasticity = {elasticity:.2f}; demand is {classify_elasticity(elasticity)}; total revenue changes from ${tr1} to ${tr2}.",
        "steps": [
            f"Percent change in quantity = ({q2} - {q1}) / [({q1} + {q2}) / 2] = {pct_q:.3f}.",
            f"Percent change in price = ({p2} - {p1}) / [({p1} + {p2}) / 2] = {pct_p:.3f}.",
            f"Elasticity = {pct_q:.3f} / {pct_p:.3f} = {elasticity:.2f}.",
            f"Total revenue before = {p1} x {q1} = ${tr1}; after = {p2} x {q2} = ${tr2}.",
        ],
        "concept": "Midpoint elasticity, classification by absolute value, and revenue interpretation.",
    }


def make_total_revenue_problem(topic: dict[str, Any], seed: int) -> dict[str, Any]:
    price_a = number_value(seed, 12, 3, 5)
    qty_a = number_value(seed, 80, 8, 5)
    price_b = price_a + number_value(seed, 3, 1, 4)
    qty_b = qty_a - number_value(seed, 10, 3, 4)
    rev_a = price_a * qty_a
    rev_b = price_b * qty_b
    change = rev_b - rev_a
    direction = "increases" if change > 0 else "decreases" if change < 0 else "does not change"
    return {
        "topic": topic["topic"],
        "prompt": (
            f"At price ${price_a}, quantity sold is {qty_a}. At price ${price_b}, quantity sold is {qty_b}. "
            "Compute total revenue in both cases and explain the change."
        ),
        "answer": f"Revenue {direction} by ${abs(change)}: from ${rev_a} to ${rev_b}.",
        "steps": [
            f"Initial total revenue = ${price_a} x {qty_a} = ${rev_a}.",
            f"New total revenue = ${price_b} x {qty_b} = ${rev_b}.",
            f"Change = ${rev_b} - ${rev_a} = ${change}.",
        ],
        "concept": "Total revenue equals price times quantity. Interpret the direction and size of the change.",
    }


def make_surplus_problem(topic: dict[str, Any], seed: int, producer: bool = False) -> dict[str, Any]:
    market_price = number_value(seed, 18, 2, 5)
    quantity = number_value(seed, 40, 5, 6)
    if producer:
        min_price = max(2, market_price - number_value(seed, 8, 1, 5))
        surplus = 0.5 * (market_price - min_price) * quantity
        prompt = (
            f"Supply starts at a minimum acceptable price of ${min_price}. Market price is ${market_price}, "
            f"and quantity sold is {quantity}. Compute producer surplus assuming a straight-line supply curve."
        )
        answer = f"Producer surplus = ${surplus:.2f}."
        steps = [
            f"Height of the surplus triangle = ${market_price} - ${min_price} = ${market_price - min_price}.",
            f"Base = quantity = {quantity}.",
            f"Producer surplus = 1/2 x {quantity} x {market_price - min_price} = ${surplus:.2f}.",
        ]
        concept = "Producer surplus is the area above supply and below price."
    else:
        max_wtp = market_price + number_value(seed, 12, 2, 5)
        surplus = 0.5 * (max_wtp - market_price) * quantity
        prompt = (
            f"The highest willingness to pay on a linear demand curve is ${max_wtp}. Market price is ${market_price}, "
            f"and quantity sold is {quantity}. Compute consumer surplus."
        )
        answer = f"Consumer surplus = ${surplus:.2f}."
        steps = [
            f"Height of the surplus triangle = ${max_wtp} - ${market_price} = ${max_wtp - market_price}.",
            f"Base = quantity = {quantity}.",
            f"Consumer surplus = 1/2 x {quantity} x {max_wtp - market_price} = ${surplus:.2f}.",
        ]
        concept = "Consumer surplus is the area below demand and above price."
    return {"topic": topic["topic"], "prompt": prompt, "answer": answer, "steps": steps, "concept": concept}


def make_deadweight_loss_problem(topic: dict[str, Any], seed: int) -> dict[str, Any]:
    tax = number_value(seed, 4, 1, 5)
    reduction = number_value(seed, 20, 4, 5)
    dwl = 0.5 * tax * reduction
    return {
        "topic": topic["topic"],
        "prompt": (
            f"A tax creates a wedge of ${tax} and reduces quantity traded by {reduction} units. "
            "Compute the deadweight loss triangle."
        ),
        "answer": f"Deadweight loss = ${dwl:.2f}.",
        "steps": [
            f"Height of the triangle = tax wedge = ${tax}.",
            f"Base of the triangle = reduction in quantity = {reduction}.",
            f"Deadweight loss = 1/2 x {tax} x {reduction} = ${dwl:.2f}.",
        ],
        "concept": "Deadweight loss is the lost total surplus from trades that no longer occur.",
    }


def make_treatment_effect_problem(topic: dict[str, Any], seed: int) -> dict[str, Any]:
    treated = number_value(seed, 74, 3, 6)
    control = treated - number_value(seed, 5, 2, 5)
    diff = treated - control
    return {
        "topic": topic["topic"],
        "prompt": (
            f"In a randomized experiment, the treatment group average outcome is {treated} and the control group average outcome is {control}. "
            "Estimate the treatment effect and state the key assumption that makes this comparison credible."
        ),
        "answer": f"Estimated treatment effect = {diff}. Credibility comes from random assignment creating comparable groups in expectation.",
        "steps": [
            f"Difference in means = treatment mean - control mean = {treated} - {control} = {diff}.",
            "Because assignment is random, the control group estimates the counterfactual outcome for the treatment group in expectation.",
            "Interpret the sign and size in the units of the outcome.",
        ],
        "concept": "Randomized experiments estimate causal effects with a difference in average outcomes.",
    }


def make_accounting_problem(topic: dict[str, Any], seed: int) -> dict[str, Any]:
    sales = number_value(seed, 8000, 500, 6)
    cogs = number_value(seed, 4200, 300, 5)
    expenses = number_value(seed, 1500, 200, 5)
    gross_profit = sales - cogs
    net_income = gross_profit - expenses
    return {
        "topic": topic["topic"],
        "prompt": (
            f"A company reports sales revenue of ${sales}, cost of goods sold of ${cogs}, and operating expenses of ${expenses}. "
            "Compute gross profit and net income, then identify which financial statement each appears on."
        ),
        "answer": f"Gross profit = ${gross_profit}; net income = ${net_income}; both appear on the income statement.",
        "steps": [
            f"Gross profit = sales revenue - cost of goods sold = ${sales} - ${cogs} = ${gross_profit}.",
            f"Net income = gross profit - operating expenses = ${gross_profit} - ${expenses} = ${net_income}.",
            "Both are income statement measures; gross profit is before operating expenses and net income is after expenses.",
        ],
        "concept": "Intermediate accounting problems often test classification, recognition, and statement effects.",
    }


def make_conceptual_problem(topic: dict[str, Any], course_type: str, seed: int) -> dict[str, Any]:
    templates = [
        (
            f"Define {topic['topic']} in two precise sentences, then give one course-specific example.",
            f"A strong answer defines {topic['topic']}, names the relevant course context, and gives a concrete example rather than a vague description.",
            ["State the definition.", "Add the course-specific context from the cited materials.", "Give one example or application."],
            "Definition plus application.",
        ),
        (
            f"Compare {topic['topic']} with a related concept from the same unit. What is the key difference an exam question might test?",
            "A strong answer identifies both concepts, states one similarity, and explains the key difference that changes the answer.",
            ["Name the related concept.", "State the similarity.", "State the tested difference and why it matters."],
            "Comparison and contrast.",
        ),
        (
            f"Write a short-answer response explaining why {topic['topic']} is important for the course's exam themes.",
            "A strong answer connects the topic to the unit's main learning objective and explains what the instructor could ask you to do with it.",
            ["Identify the exam theme.", "Explain how the topic fits the theme.", "End with an application or likely question style."],
            "Short-answer explanation.",
        ),
    ]
    prompt, answer, steps, concept = templates[seed % len(templates)]
    if course_type == "quantitative":
        steps = steps + ["If numbers are provided on the exam, write the formula or rule before substituting values."]
    return {"topic": topic["topic"], "prompt": prompt, "answer": answer, "steps": steps, "concept": concept}


def make_practice_problem(topic: dict[str, Any], course_type: str, seed: int) -> dict[str, Any]:
    key = topic["topic_key"].lower()
    if "elasticity" in key:
        return make_elasticity_problem(topic, seed)
    if "total revenue" in key or key == "revenue":
        return make_total_revenue_problem(topic, seed)
    if "consumer surplus" in key:
        return make_surplus_problem(topic, seed)
    if "producer surplus" in key:
        return make_surplus_problem(topic, seed, producer=True)
    if "deadweight" in key or "tax" in key:
        return make_deadweight_loss_problem(topic, seed)
    if any(term in key for term in ["treatment", "experimental", "experiment", "potential outcome", "unconfounded", "identification"]):
        return make_treatment_effect_problem(topic, seed)
    if any(term in key for term in ["accounting", "revenue recognition", "inventory", "income statement", "balance sheet"]):
        return make_accounting_problem(topic, seed)
    if course_type == "quantitative" and seed % 3 == 0:
        return make_treatment_effect_problem(topic, seed)
    return make_conceptual_problem(topic, course_type, seed)


def build_practice_set(
    exam_map: dict[str, Any],
    topic_query: str | None = None,
    top: int = 6,
    max_topics: int = 5,
    problems_per_topic: int = 2,
    title: str | None = None,
    kind: str = "practice exam",
) -> dict[str, Any]:
    course_type = exam_map.get("course_type", "mixed")
    topics = choose_practice_topics(exam_map, topic_query, top, max_topics)
    problems: list[dict[str, Any]] = []
    serial = 1
    for topic_idx, topic in enumerate(topics, start=1):
        for local_idx in range(problems_per_topic):
            problem = make_practice_problem(topic, course_type, seed=(topic_idx * 10 + local_idx))
            problem["number"] = serial
            problem["source_priority"] = topic["priority"]
            problem["source_score"] = topic["score"]
            problem["sources"] = topic.get("sources", [])[:3]
            problems.append(problem)
            serial += 1
    if not title:
        title = "Practice Exam" if kind == "practice exam" else "Topic-Specific Problem Set"
    return {
        "title": title,
        "kind": kind,
        "course_type": course_type,
        "topics": topics,
        "problems": problems,
        "created_at": now_iso(),
    }


def group_problems_by_topic(problems: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for problem in problems:
        grouped[problem["topic"]].append(problem)
    return grouped


def html_document(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      color: #1f2933;
      line-height: 1.45;
      margin: 0;
      background: #f7f8fa;
    }}
    .page {{
      width: 8.5in;
      min-height: 11in;
      margin: 24px auto;
      background: white;
      padding: 0.65in;
      box-shadow: 0 1px 8px rgba(0,0,0,0.08);
      box-sizing: border-box;
    }}
    h1 {{
      font-size: 25px;
      margin: 0 0 8px;
      letter-spacing: 0;
    }}
    h2 {{
      font-size: 16px;
      margin: 28px 0 10px;
      padding-bottom: 6px;
      border-bottom: 1px solid #cfd7df;
      letter-spacing: 0;
    }}
    .meta {{
      font-size: 12px;
      color: #627386;
      margin-bottom: 22px;
    }}
    .problem {{
      margin: 0 0 22px;
      page-break-inside: avoid;
    }}
    .problem-title {{
      font-weight: 700;
      margin-bottom: 6px;
    }}
    .prompt {{
      margin-bottom: 12px;
    }}
    .answer-space {{
      height: 92px;
      border: 1px solid #d8dee6;
      border-radius: 4px;
      background: repeating-linear-gradient(white, white 29px, #edf1f5 30px);
    }}
    ol.steps {{
      margin-top: 8px;
    }}
    .concept {{
      color: #435466;
      font-size: 13px;
      margin-top: 6px;
    }}
    @media print {{
      body {{ background: white; }}
      .page {{ box-shadow: none; margin: 0; width: auto; min-height: auto; }}
    }}
  </style>
</head>
<body>
  <main class="page">
{body}
  </main>
</body>
</html>
"""


def render_worksheet_html(practice_set: dict[str, Any]) -> str:
    parts = [
        f"    <h1>{html.escape(practice_set['title'])}</h1>",
        f"    <div class=\"meta\">Course type: {html.escape(practice_set['course_type'])} | Generated {html.escape(practice_set['created_at'])}</div>",
    ]
    grouped = group_problems_by_topic(practice_set["problems"])
    for topic, problems in grouped.items():
        parts.append(f"    <h2>{html.escape(topic)}</h2>")
        for problem in problems:
            parts.append("    <section class=\"problem\">")
            parts.append(f"      <div class=\"problem-title\">{problem['number']}. {html.escape(problem['topic'])}</div>")
            parts.append(f"      <div class=\"prompt\">{html.escape(problem['prompt'])}</div>")
            parts.append("      <div class=\"answer-space\"></div>")
            parts.append("    </section>")
    return html_document(practice_set["title"], "\n".join(parts))


def render_answer_key_html(practice_set: dict[str, Any]) -> str:
    parts = [
        f"    <h1>{html.escape(practice_set['title'])} - Answer Key</h1>",
        f"    <div class=\"meta\">Course type: {html.escape(practice_set['course_type'])} | Generated {html.escape(practice_set['created_at'])}</div>",
    ]
    grouped = group_problems_by_topic(practice_set["problems"])
    for topic, problems in grouped.items():
        parts.append(f"    <h2>{html.escape(topic)}</h2>")
        for problem in problems:
            parts.append("    <section class=\"problem\">")
            parts.append(f"      <div class=\"problem-title\">{problem['number']}. Final answer</div>")
            parts.append(f"      <div>{html.escape(problem['answer'])}</div>")
            parts.append("      <ol class=\"steps\">")
            for step in problem["steps"]:
                parts.append(f"        <li>{html.escape(step)}</li>")
            parts.append("      </ol>")
            parts.append(f"      <div class=\"concept\">Concept used: {html.escape(problem['concept'])}</div>")
            parts.append("    </section>")
    return html_document(practice_set["title"] + " - Answer Key", "\n".join(parts))


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def add_wrapped_pdf_line(lines: list[tuple[str, str, int, int]], text: str, font: str = "F1", size: int = 10, gap: int = 4) -> None:
    width = max(36, int(92 * (10 / size)))
    wrapped = textwrap.wrap(text, width=width) or [""]
    for idx, line in enumerate(wrapped):
        lines.append((line, font, size, gap if idx == len(wrapped) - 1 else 2))


def practice_set_to_pdf_lines(practice_set: dict[str, Any], answer_key: bool = False) -> list[tuple[str, str, int, int]]:
    lines: list[tuple[str, str, int, int]] = []
    title = practice_set["title"] + (" - Answer Key" if answer_key else "")
    add_wrapped_pdf_line(lines, title, "F2", 18, 8)
    add_wrapped_pdf_line(lines, f"Course type: {practice_set['course_type']} | Generated {practice_set['created_at']}", "F1", 9, 12)
    grouped = group_problems_by_topic(practice_set["problems"])
    for topic, problems in grouped.items():
        add_wrapped_pdf_line(lines, topic, "F2", 13, 8)
        for problem in problems:
            add_wrapped_pdf_line(lines, f"{problem['number']}. {problem['prompt']}", "F1", 10, 8)
            if answer_key:
                add_wrapped_pdf_line(lines, f"Final answer: {problem['answer']}", "F2", 10, 5)
                for idx, step in enumerate(problem["steps"], start=1):
                    add_wrapped_pdf_line(lines, f"Step {idx}: {step}", "F1", 10, 3)
                add_wrapped_pdf_line(lines, f"Concept used: {problem['concept']}", "F1", 9, 10)
            else:
                for _ in range(4):
                    add_wrapped_pdf_line(lines, "____________________________________________________________", "F1", 10, 3)
                lines.append(("", "F1", 10, 8))
    return lines


def write_simple_pdf(path: Path, lines: list[tuple[str, str, int, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    page_width, page_height = 612, 792
    margin = 54
    y_start = page_height - margin
    y_min = margin
    pages: list[list[str]] = [[]]
    y = y_start
    for text, font, size, gap in lines:
        line_height = size + gap
        if y - line_height < y_min:
            pages.append([])
            y = y_start
        pages[-1].append(f"BT /{font} {size} Tf {margin} {y} Td ({pdf_escape(text)}) Tj ET")
        y -= line_height

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kid_refs = " ".join(f"{5 + i * 2} 0 R" for i in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kid_refs}] /Count {len(pages)} >>".encode("latin-1"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    for idx, page_lines in enumerate(pages):
        page_id = 5 + idx * 2
        content_id = page_id + 1
        content = "\n".join(page_lines).encode("latin-1", errors="replace")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>".encode("latin-1")
        )
        objects.append(b"<< /Length " + str(len(content)).encode("latin-1") + b" >>\nstream\n" + content + b"\nendstream")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj_id, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{obj_id} 0 obj\n".encode("latin-1"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    pdf.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("latin-1")
    )
    path.write_bytes(bytes(pdf))


def export_practice_set(practice_set: dict[str, Any], out_dir: Path, base_name: str, output_format: str) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    worksheet_html = render_worksheet_html(practice_set)
    answer_html = render_answer_key_html(practice_set)
    if output_format in {"html", "both"}:
        worksheet_path = out_dir / f"{base_name}_worksheet.html"
        answer_path = out_dir / f"{base_name}_answer_key.html"
        worksheet_path.write_text(worksheet_html, encoding="utf-8")
        answer_path.write_text(answer_html, encoding="utf-8")
        paths["worksheet_html"] = worksheet_path
        paths["answer_key_html"] = answer_path
    if output_format in {"pdf", "both"}:
        worksheet_pdf = out_dir / f"{base_name}_worksheet.pdf"
        answer_pdf = out_dir / f"{base_name}_answer_key.pdf"
        write_simple_pdf(worksheet_pdf, practice_set_to_pdf_lines(practice_set, answer_key=False))
        write_simple_pdf(answer_pdf, practice_set_to_pdf_lines(practice_set, answer_key=True))
        paths["worksheet_pdf"] = worksheet_pdf
        paths["answer_key_pdf"] = answer_pdf
    metadata_path = out_dir / f"{base_name}_metadata.json"
    write_json(metadata_path, practice_set)
    paths["metadata"] = metadata_path
    return paths


def default_practice_output_dir(state_dir: Path) -> Path:
    return Path("practice_sets") / slugify(state_dir.name, "course")


def command_practice(args: argparse.Namespace) -> None:
    state_dir = Path(args.state)
    exam_map = load_exam_map(state_dir)
    make_exam = args.exam or not args.topic
    kind = "practice exam" if make_exam else "topic-specific problem set"
    topic_query = args.topic
    if make_exam:
        topic_query = None
    practice_set = build_practice_set(
        exam_map,
        topic_query=topic_query,
        top=args.top,
        max_topics=1 if topic_query else args.topics,
        problems_per_topic=args.problems_per_topic,
        title=args.title,
        kind=kind,
    )
    out_dir = Path(args.out_dir) if args.out_dir else default_practice_output_dir(state_dir)
    base_name = slugify(args.name or practice_set["title"])
    paths = export_practice_set(practice_set, out_dir, base_name, args.format)
    print(f"Generated {practice_set['title']} with {len(practice_set['problems'])} problems.")
    for label, path in paths.items():
        print(f"- {label.replace('_', ' ').title()}: {path}")


def command_teach(args: argparse.Namespace) -> None:
    state_dir = Path(args.state)
    exam_map = load_exam_map(state_dir)
    topic = find_topic(exam_map, args.topic, args.top)
    teach_topic(topic, exam_map.get("course_type", "mixed"), state_dir)


def command_quiz(args: argparse.Namespace) -> None:
    state_dir = Path(args.state)
    exam_map = load_exam_map(state_dir)
    topics = exam_map.get("topics", [])[: args.topics]
    questions = make_quiz_questions(topics, exam_map.get("course_type", "mixed"), args.count)
    progress = load_progress(state_dir)

    if args.interactive:
        print("Interactive quiz. Answer briefly; the agent will score keyword coverage and you can override it.")
        for idx, question in enumerate(questions, start=1):
            print()
            print_wrapped(f"{idx}. {question['question']}")
            answer = input("> ").strip()
            estimated = score_answer(answer, question["expected_terms"])
            print(f"Estimated coverage: {round(estimated * 100)}%")
            if question["expected_terms"]:
                print(f"Expected cues: {', '.join(question['expected_terms'][:6])}")
            override = input("Mark correct? [y/n/enter to accept estimate] ").strip().lower()
            if override.startswith("y"):
                score = 1.0
            elif override.startswith("n"):
                score = 0.0
            else:
                score = estimated
            progress.setdefault("quiz_history", []).append(
                {
                    "at": now_iso(),
                    "topic": question["topic"],
                    "topic_key": question["topic_key"],
                    "question": question["question"],
                    "score": score,
                }
            )
            update_weakness(progress, question["topic_key"], question["topic"], score)
        save_progress(state_dir, progress)
        print("\nSaved quiz results.")
    else:
        print("Quiz:")
        for idx, question in enumerate(questions, start=1):
            print_wrapped(f"{idx}. {question['question']}")
        print("\nAnswer key cues:")
        for idx, question in enumerate(questions, start=1):
            print_wrapped(f"{idx}. {question['topic']}: {', '.join(question['expected_terms'][:6]) or 'use the cited course evidence'}")


def update_weakness(progress: dict[str, Any], topic_key: str, topic_name: str, score: float) -> None:
    weakness = progress.setdefault("weakness", {}).setdefault(
        topic_key,
        {"topic": topic_name, "attempts": 0, "average_score": 0.0, "weakness_score": 0.0},
    )
    attempts = weakness["attempts"] + 1
    average = ((weakness["average_score"] * weakness["attempts"]) + score) / attempts
    weakness["attempts"] = attempts
    weakness["average_score"] = round(average, 3)
    weakness["weakness_score"] = round(1.0 - average, 3)
    weakness["last_seen_at"] = now_iso()


def command_weakest(args: argparse.Namespace) -> None:
    progress = load_progress(Path(args.state))
    weakness = list(progress.get("weakness", {}).values())
    if not weakness:
        print("No quiz history yet. Run an interactive quiz first:")
        print("python3 study_agent.py quiz --interactive")
        return
    weakness.sort(key=lambda item: (item["weakness_score"], item["attempts"]), reverse=True)
    print("Weakest topics:")
    for item in weakness[: args.limit]:
        print(f"- {item['topic']}: weakness {round(item['weakness_score'] * 100)}%, attempts {item['attempts']}")


def command_plan(args: argparse.Namespace) -> None:
    state_dir = Path(args.state)
    exam_map = load_exam_map(state_dir)
    print(make_study_plan(exam_map, args.hours))
    print()
    print(make_strategy_insights_text(exam_map, state_dir))


def make_study_plan(exam_map: dict[str, Any], hours: float) -> str:
    topics = exam_map.get("topics", [])
    if not topics:
        return "No topics available yet."
    total_minutes = max(30, int(hours * 60))
    high = [t for t in topics if t["priority"] == "very likely exam material"]
    possible = [t for t in topics if t["priority"] == "possibly testable material"]
    selected = (high + possible)[: max(4, min(12, total_minutes // 15))]
    if not selected:
        selected = topics[: max(4, min(10, total_minutes // 15))]
    per_topic = max(8, int(total_minutes * 0.68 / len(selected)))
    review_minutes = max(10, total_minutes - per_topic * len(selected))

    lines = [f"{hours:g}-hour exam-focused study plan", ""]
    lines.append("Priority order:")
    for idx, topic in enumerate(selected, start=1):
        lines.append(f"{idx}. {topic['topic']} ({topic['score']}/100, {topic['confidence']} confidence)")
    lines.append("")
    lines.append("Session structure:")
    for topic in selected:
        lines.append(f"- {per_topic} min: learn and actively recall {topic['topic']}. End by answering one likely exam question.")
    lines.append(f"- {review_minutes} min: mixed quiz, fix weak spots, then write a one-page cheat sheet from memory.")
    review_insights = exam_map.get("review_insights", {})
    teaching_styles = review_insights.get("strategy_modifiers", {}).get("teaching_style", [])
    study_strategy_lines = category_lines(review_insights, "study_strategies", limit=3) if review_insights.get("status") == "found" else []
    if teaching_styles or study_strategy_lines:
        lines.append("")
        lines.append("How to study for this class:")
        for style in teaching_styles[:3]:
            lines.append(f"- {style}.")
        for strategy in study_strategy_lines[:3]:
            lines.append(f"- Student-reported: {strategy}")
    lines.append("")
    lines.append("Rule: skip low-priority topics unless you can already answer the high-priority questions cleanly.")
    return "\n".join(lines)


def command_review(args: argparse.Namespace) -> None:
    state_dir = Path(args.state)
    exam_map = load_exam_map(state_dir)
    print(make_review_sheet(exam_map, args.limit))
    print()
    print(make_strategy_insights_text(exam_map, state_dir))


def make_review_sheet(exam_map: dict[str, Any], limit: int = 12) -> str:
    topics = exam_map.get("topics", [])[:limit]
    course_type = exam_map.get("course_type", "mixed")
    lines = ["Most Likely On The Exam: Cheat-Sheet Review", ""]
    buckets = ["very likely exam material", "possibly testable material", "low-priority material"]
    for bucket in buckets:
        bucket_topics = [topic for topic in topics if topic["priority"] == bucket]
        if not bucket_topics:
            continue
        lines.append(bucket.title())
        for topic in bucket_topics:
            lines.append(f"- {topic['topic']} ({topic['score']}/100, {topic['confidence']} confidence)")
            lines.append(f"  Why: {topic['rationale']}")
            q = likely_question_templates(topic, course_type)[0]
            lines.append(f"  Be ready to: {q}")
            if topic["sources"]:
                lines.append(f"  Evidence: {topic['sources'][0]['file']} :: {topic['sources'][0]['section']}")
        lines.append("")
    lines.append("Final pass: cover the topic names, define each from memory, then solve/explain one exam-style prompt for each very-likely topic.")
    return "\n".join(lines)


def command_predict(args: argparse.Namespace) -> None:
    state_dir = Path(args.state)
    exam_map = load_exam_map(state_dir)
    print_topic_table(exam_map.get("topics", []), args.limit)
    print(make_strategy_insights_text(exam_map, state_dir))


def command_chat(args: argparse.Namespace) -> None:
    state_dir = Path(args.state)
    exam_map = load_exam_map(state_dir)
    print("Canvas Study Agent")
    print("Try: teach me unit 3 | quiz me | generate practice exam | problem set on <topic> | predict 10 | review | exit")
    while True:
        try:
            command = input("\nstudy> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not command:
            continue
        if command.lower() in {"exit", "quit"}:
            return
        handle_chat_command(command, exam_map, state_dir)


def handle_chat_command(command: str, exam_map: dict[str, Any], state_dir: Path) -> None:
    lower = command.lower()
    if "weak" in lower:
        args = argparse.Namespace(state=str(state_dir), limit=8)
        command_weakest(args)
        return
    if "quiz" in lower:
        count_match = re.search(r"\b(\d+)\b", lower)
        count = int(count_match.group(1)) if count_match else 5
        args = argparse.Namespace(state=str(state_dir), topics=6, count=count, interactive=True)
        command_quiz(args)
        return
    if "practice exam" in lower or ("generate" in lower and "exam" in lower):
        args = argparse.Namespace(
            state=str(state_dir),
            exam=True,
            topic=None,
            top=8,
            topics=5,
            problems_per_topic=2,
            format="both",
            out_dir=None,
            name=None,
            title=None,
        )
        command_practice(args)
        return
    if "problem set" in lower or ("practice" in lower and "topic" in lower):
        topic_query = ""
        match = re.search(r"\b(?:on|for|about)\s+(.+)$", command, re.I)
        if match:
            topic_query = match.group(1).strip()
        args = argparse.Namespace(
            state=str(state_dir),
            exam=False,
            topic=topic_query or None,
            top=8,
            topics=1,
            problems_per_topic=6,
            format="both",
            out_dir=None,
            name=None,
            title=None,
        )
        command_practice(args)
        return
    if "cram" in lower or "plan" in lower:
        hours_match = re.search(r"(\d+(?:\.\d+)?)\s*[- ]?hour", lower)
        hours = float(hours_match.group(1)) if hours_match else 2.0
        print(make_study_plan(exam_map, hours))
        print()
        print(make_strategy_insights_text(exam_map, state_dir))
        return
    if "predict" in lower or "likely" in lower or "top" in lower:
        limit_match = re.search(r"\b(\d+)\b", lower)
        limit = int(limit_match.group(1)) if limit_match else 10
        print_topic_table(exam_map.get("topics", []), limit)
        print(make_strategy_insights_text(exam_map, state_dir))
        return
    if "review" in lower or "cheat" in lower:
        print(make_review_sheet(exam_map, 12))
        print()
        print(make_strategy_insights_text(exam_map, state_dir))
        return
    if "teach" in lower:
        query = re.sub(r"teach( me)?", "", command, flags=re.I).strip()
        try:
            topic = find_topic(exam_map, query or None)
            teach_topic(topic, exam_map.get("course_type", "mixed"), state_dir)
        except SystemExit as exc:
            print(exc)
        return
    try:
        topic = find_topic(exam_map, command)
        teach_topic(topic, exam_map.get("course_type", "mixed"), state_dir)
    except SystemExit:
        print("I did not recognize that. Try 'predict 10', 'teach me <topic>', 'quiz me', 'weakest', or 'review'.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Canvas exam study agent")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="Folder for generated index, map, and progress files")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_state_arg(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument(
            "--state",
            default=argparse.SUPPRESS,
            help="Folder for generated index, map, and progress files",
        )

    p_index = sub.add_parser("index", help="Read and chunk Canvas course files")
    add_state_arg(p_index)
    p_index.add_argument("--course", default=str(DEFAULT_COURSE), help="Folder containing Canvas files")
    p_index.set_defaults(func=command_index)

    p_sort = sub.add_parser("sort-files", help="Copy or move downloaded Canvas files into course folders")
    p_sort.add_argument("--source", required=True, help="Folder to scan, such as ~/Downloads or a Canvas export folder")
    p_sort.add_argument("--dest", default=str(DEFAULT_COURSE), help="Destination root containing course folders")
    p_sort.add_argument(
        "--courses",
        nargs="*",
        default=DEFAULT_SORT_COURSES,
        help="Course codes to sort into, e.g. ECON 404 ECON 440 ECON 470 BUS 321",
    )
    p_sort.add_argument("--move", action="store_true", help="Move files instead of copying them")
    p_sort.add_argument("--dry-run", action="store_true", help="Show what would happen without copying or moving")
    p_sort.add_argument("--no-content-scan", action="store_true", help="Only use filenames and paths, not file contents")
    p_sort.add_argument("--include-unmatched", action="store_true", help="Copy/move unmatched files into canvas_files/_unsorted")
    p_sort.set_defaults(func=command_sort_files)

    p_rank = sub.add_parser("rank", help="Build exam-likelihood topic map")
    add_state_arg(p_rank)
    p_rank.add_argument("--limit", type=int, default=15)
    p_rank.add_argument("--with-reviews", action="store_true", help="Fetch Polyratings insights before ranking")
    p_rank.add_argument("--api-base", default=POLYRATINGS_API_BASE, help="Polyratings API base URL")
    p_rank.set_defaults(func=command_rank)

    p_reviews = sub.add_parser("reviews", help="Fetch and summarize Polyratings professor/course review insights")
    add_state_arg(p_reviews)
    p_reviews.add_argument("--api-base", default=POLYRATINGS_API_BASE, help="Polyratings API base URL")
    p_reviews.set_defaults(func=command_reviews)

    p_strategy = sub.add_parser("strategy", help="Print syllabus, Polyratings, and agent strategy insights")
    add_state_arg(p_strategy)
    p_strategy.set_defaults(func=command_strategy)

    p_predict = sub.add_parser("predict", help="Print predicted likely exam topics")
    add_state_arg(p_predict)
    p_predict.add_argument("--limit", type=int, default=10)
    p_predict.set_defaults(func=command_predict)

    p_teach = sub.add_parser("teach", help="Teach a topic")
    add_state_arg(p_teach)
    p_teach.add_argument("topic", nargs="?", help="Topic name, unit, or keyword")
    p_teach.add_argument("--top", type=int, help="Teach the Nth ranked topic")
    p_teach.set_defaults(func=command_teach)

    p_quiz = sub.add_parser("quiz", help="Generate or run a quiz")
    add_state_arg(p_quiz)
    p_quiz.add_argument("--topics", type=int, default=5, help="Use the top N topics")
    p_quiz.add_argument("--count", type=int, default=5, help="Number of questions")
    p_quiz.add_argument("--interactive", action="store_true", help="Ask questions and track performance")
    p_quiz.set_defaults(func=command_quiz)

    p_practice = sub.add_parser("practice", help="Generate clean worksheet-style practice problems and an answer key")
    add_state_arg(p_practice)
    p_practice.add_argument("--exam", action="store_true", help="Generate a multi-topic practice exam")
    p_practice.add_argument("--topic", help="Generate a topic-specific problem set for this topic")
    p_practice.add_argument("--top", type=int, default=8, help="Consider the top N ranked topics")
    p_practice.add_argument("--topics", type=int, default=5, help="Number of topics to include in a practice exam")
    p_practice.add_argument("--problems-per-topic", type=int, default=2, help="Problems to generate per topic")
    p_practice.add_argument("--format", choices=["pdf", "html", "both"], default="both", help="Export format")
    p_practice.add_argument("--out-dir", help="Output folder for generated worksheet and answer key")
    p_practice.add_argument("--name", help="Base filename for generated files")
    p_practice.add_argument("--title", help="Worksheet title")
    p_practice.set_defaults(func=command_practice)

    p_plan = sub.add_parser("plan", help="Make a cram/study plan")
    add_state_arg(p_plan)
    p_plan.add_argument("--hours", type=float, default=2.0)
    p_plan.set_defaults(func=command_plan)

    p_weakest = sub.add_parser("weakest", help="Show weakest topics from interactive quiz history")
    add_state_arg(p_weakest)
    p_weakest.add_argument("--limit", type=int, default=8)
    p_weakest.set_defaults(func=command_weakest)

    p_review = sub.add_parser("review", help="Create final cheat-sheet style review")
    add_state_arg(p_review)
    p_review.add_argument("--limit", type=int, default=12)
    p_review.set_defaults(func=command_review)

    p_chat = sub.add_parser("chat", help="Start interactive study session")
    add_state_arg(p_chat)
    p_chat.set_defaults(func=command_chat)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
