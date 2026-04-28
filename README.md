# Canvas Exam Study Agent

A local study agent that reads Canvas course materials, predicts the most likely exam content, and teaches it back in an active-recall tutoring style.

This first version assumes your Canvas files are already accessible locally. Export/download the course files from Canvas, then place them in `canvas_files/<course-name>/` or point the agent at any folder with `--course`.

## What It Does

1. Builds a structured index of course materials.
2. Starts with the syllabus when available, extracting course name, course code, instructor, grading breakdown, exam weighting, learning objectives, important topics, and exam guidance.
3. Chunks files into citable sections.
4. Infers each file's role: lecture slides, lecture notes, study guide, review sheet, quiz, assignment, practice exam, reading, discussion, syllabus, or unknown.
5. Optionally fetches professor/course review patterns from `polyratings.dev`.
6. Scores likely exam topics using repetition, learning objectives, headings, review materials, examples, homework/quiz/exam appearances, instructor-emphasis phrases, and reliable student-reported review patterns.
7. Produces an exam-likelihood map with scores, rationale, confidence, priority, and source citations.
8. Enters tutoring mode: teach, quiz, cram plan, weakest topics, and final review sheet.

## Quick Start

Create a course folder and put your Canvas files inside it:

```bash
mkdir -p canvas_files/my_course
```

Then run:

```bash
python3 study_agent.py index --course canvas_files/my_course --state state/my_course
python3 study_agent.py rank --state state/my_course --limit 15
python3 study_agent.py chat --state state/my_course
```

To include Polyratings strategy insights after the syllabus has been indexed:

```bash
python3 study_agent.py reviews --state state/my_course
python3 study_agent.py rank --state state/my_course --with-reviews --limit 15
```

`reviews` and `rank --with-reviews` require internet access. If no professor match or reviews are found, the agent continues normally and says review insights are unavailable.

## Sorting Downloaded Canvas Files

The agent can sort already-downloaded Canvas files into course folders. It looks for course codes in filenames, folder paths, and file contents.

Your folders are:

```text
canvas_files/
  ECON 404/
  ECON 440/
  ECON 470/
  BUS 321/
```

Known course-name aliases:

- `BUS 321`: `Intermediate Accounting 1`, `Intermediate Accounting I`, `Intermediate Accounting One`

Preview the sort first:

```bash
python3 study_agent.py sort-files --source ~/Downloads --dry-run
```

Copy matching files into the right course folders:

```bash
python3 study_agent.py sort-files --source ~/Downloads
```

Move files instead of copying them:

```bash
python3 study_agent.py sort-files --source ~/Downloads --move
```

Sort from a Canvas export folder:

```bash
python3 study_agent.py sort-files --source ~/Downloads/canvas-export
```

The sorter is intentionally conservative. If it cannot confidently identify a class, it leaves the file unmatched. To collect unmatched files into a review folder:

```bash
python3 study_agent.py sort-files --source ~/Downloads --include-unmatched
```

Direct Canvas downloading is not automatic unless Canvas files are already exported/downloaded locally or Canvas API access is added. The safest workflow is: download/export files from Canvas, run `sort-files`, then index each course.

To test the tool with the included fictional sample course:

```bash
python3 study_agent.py index --course examples/sample_course --state state/sample
python3 study_agent.py rank --state state/sample --limit 10
python3 study_agent.py teach --state state/sample --top 2
```

Useful direct commands:

```bash
python3 study_agent.py predict --state state/my_course --limit 10
python3 study_agent.py reviews --state state/my_course
python3 study_agent.py strategy --state state/my_course
python3 study_agent.py teach --state state/my_course --top 1
python3 study_agent.py teach --state state/my_course "unit 3"
python3 study_agent.py quiz --state state/my_course --count 8
python3 study_agent.py quiz --state state/my_course --interactive
python3 study_agent.py practice --state state/my_course --exam
python3 study_agent.py practice --state state/my_course --topic "price elasticity of demand"
python3 study_agent.py weakest --state state/my_course
python3 study_agent.py plan --state state/my_course --hours 2
python3 study_agent.py review --state state/my_course --limit 12
```

Inside `chat`, try:

```text
teach me unit 3
quiz me on the highest-yield material
generate practice exam
generate topic-specific problem set on price elasticity of demand
what am I weakest on?
make me a 2-hour cram plan
predict the 10 most likely exam topics
review
```

## Practice Problem Sets And PDFs

Generate a clean worksheet and separate answer key from the highest-priority topics:

```bash
python3 study_agent.py practice --state state/my_course --exam
```

Generate a topic-specific problem set:

```bash
python3 study_agent.py practice --state state/my_course --topic "price elasticity of demand"
```

Export options:

```bash
python3 study_agent.py practice --state state/my_course --exam --format pdf
python3 study_agent.py practice --state state/my_course --exam --format html
python3 study_agent.py practice --state state/my_course --exam --format both
```

Outputs are saved under `practice_sets/<course>/` by default:

- worksheet PDF/HTML
- separate answer key PDF/HTML
- metadata JSON

Problem style adapts to the course:

- quantitative courses: calculation, multi-step, worked-solution style
- conceptual courses: definitions, short answers, comparisons, and explanations

## Supported Files

The agent reads:

- Text, Markdown, CSV, TSV, JSON, HTML
- DOCX
- PPTX
- XLSX
- PDF when `pypdf`, `PyPDF2`, or `pdftotext` is installed

If PDF extraction is unavailable, the agent will warn you and continue with the rest of the course files.

## Output Files

For each course state folder:

- `course_index.json`: structured file and chunk index
- `syllabus_analysis.json`: course identity, instructor, grading/exam signals, learning objectives, and exam guidance extracted from the syllabus
- `review_insights.json`: student-reported Polyratings patterns, reliability labels, and strategy modifiers when review lookup has been run
- `exam_map.json`: ranked topic map with rationale and citations
- `progress.json`: covered topics, quiz attempts, and weak areas

## Professor & Course Strategy Insights

Recommendation outputs include a section called `Professor & Course Strategy Insights` with three explicitly separated sources:

- `From syllabus/materials`: extracted course details, exam weighting, learning objectives, and stated exam guidance.
- `From student reviews (polyratings.dev)`: student-reported strategies, exam patterns, difficult areas, time-management advice, and pitfalls. These are marked as student-reported and weighted by recurrence.
- `Agent inference`: how the agent adjusts topic priority and teaching style from the syllabus, materials, and reliable review patterns.

Review reliability rules:

- Patterns in multiple reviews are prioritized.
- Isolated or extreme comments are downweighted.
- Review insights never override course materials by themselves.
- If no reviews are found, no review insight is fabricated.

## Assumptions

- Canvas files are already local or mounted through a connected source.
- File names and folder names often contain useful signals, such as `exam review`, `quiz`, `lecture slides`, or `homework`.
- No model API key is required for the deterministic version. The prompt files in `prompts/` show how to wrap the same index and exam map with an LLM tutor.
- The rankings are predictions, not guarantees. When evidence is thin, the agent marks confidence as low or medium.

## Best Results

Include as many of these as possible:

- Syllabus
- Lecture slides and notes
- Review sheets and study guides
- Assignments and homework
- Quizzes
- Practice exams or past exams
- Reading notes and discussion prompts

The highest-quality predictions come when review/practice materials overlap with repeated lecture and assignment topics.
