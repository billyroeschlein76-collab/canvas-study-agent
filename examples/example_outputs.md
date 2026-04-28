# Example Outputs

These examples use a fictional economics course. Your real outputs will cite your actual Canvas files.

## Deliverable 5A: Topic Ranking

```text
1. Price Elasticity Of Demand [very likely exam material; score 100/100; high confidence]
   appears in review or study-guide material; shows up in homework/quiz-style assessment material;
   repeats across 5 files; linked to learning-objective language; supported by examples or practice
   problems; student-reported Polyratings patterns modestly increase its priority. Confidence is
   high; normalized score 100.0/100.
   - Final_Review.md :: Unit 3 Review (learning objective, emphasis)
   - Homework_04.docx :: Elasticity Problems (example problem, assessment)
   - Lecture_07_Slides.pptx :: Elasticity And Revenue (heading, formula)

2. Consumer Surplus [very likely exam material; score 86.4/100; high confidence]
   appears in review or study-guide material; repeats across 4 files; supported by examples or
   practice problems. Confidence is high; normalized score 86.4/100.
   - Study_Guide.md :: Welfare Analysis
   - Quiz_03.csv :: Question Bank
   - Lecture_08_Notes.md :: Surplus And Deadweight Loss

3. Deadweight Loss [possibly testable material; score 58.2/100; medium confidence]
   shows up in homework/quiz-style assessment material; repeats across 2 files. Confidence is
   medium; normalized score 58.2/100.
   - Homework_05.docx :: Tax Incidence
   - Lecture_08_Notes.md :: Surplus And Deadweight Loss

Professor & Course Strategy Insights

From syllabus/materials
- Course: ECON 201 Principles of Microeconomics
- Instructor: Parisa Mahjoor
- Exam/grading signal: Midterm Exam: 25%
- Exam/grading signal: Final Exam: 35%
- Exam guidance: the final is cumulative and emphasizes elasticity, welfare analysis, and homework-style calculation problems.

From student reviews (polyratings.dev)
- Study strategies: Students report that lecture notes/slides matter. (recurring student-reported pattern; 10 supporting reviews)
- Exam patterns: Students mention quizzes as useful signals. (recurring student-reported pattern; 9 supporting reviews)
- Pitfalls: Students describe the material as difficult or confusing. (recurring student-reported pattern; 10 supporting reviews)

Agent inference
- Topic ranking is modestly adjusted toward lecture, quiz, review-guide, and homework-style material.
- Teaching should use more worked examples, frequent short quizzes, and trap checks.
```

## Deliverable 5B: Teaching Session

```text
# Price Elasticity Of Demand
Priority: very likely exam material | Score: 100/100 | Confidence: high

Why this is likely testable:
  It appears in the final review, homework problems, quiz material, and lecture slides. It also
  repeats across multiple files and is tied to learning-objective language.

Simple explanation:
  Price elasticity of demand measures how strongly quantity demanded responds when price changes.
  If demand is elastic, quantity changes a lot. If demand is inelastic, quantity changes only a
  little.

Core ideas to know:
  - Formula: percent change in quantity demanded divided by percent change in price.
  - Elastic demand usually has absolute value greater than 1.
  - Inelastic demand usually has absolute value less than 1.
  - Total revenue rises after a price cut only when demand is elastic.

Likely exam question styles:
  - Given prices and quantities, calculate elasticity using the midpoint method.
  - Decide whether demand is elastic or inelastic.
  - Predict what happens to total revenue after a price change.

Worked example pattern:
  1. Identify old and new price and quantity.
  2. Calculate percent change in quantity using midpoint.
  3. Calculate percent change in price using midpoint.
  4. Divide quantity percent change by price percent change.
  5. Interpret elastic vs. inelastic and connect to revenue.

Common traps:
  - Forgetting to use absolute value when classifying elasticity.
  - Mixing up movement along demand with a shift in demand.
  - Calculating correctly but not interpreting revenue.

Short quiz:
  1. What does price elasticity measure?
  2. What does elasticity greater than 1 mean?
  3. If demand is inelastic, what happens to revenue when price rises?

Professor & Course Strategy Insights
From syllabus/materials: the final exam is high-weight and emphasizes homework-style calculations.
From student reviews (polyratings.dev): students repeatedly mention lectures/slides and quizzes as useful study signals.
Agent inference: practice calculation patterns first, then quiz common traps.
```

## Deliverable 5C: Quiz Session

```text
Interactive quiz. Answer briefly; the agent will score keyword coverage and you can override it.

1. What information would you identify first before solving a Price Elasticity Of Demand problem?
> old price, new price, old quantity, new quantity
Estimated coverage: 83%
Expected cues: price, quantity, midpoint, change, demand
Mark correct? [y/n/enter to accept estimate]

2. What is one common calculation or interpretation trap for Price Elasticity Of Demand?
> forgetting absolute value
Estimated coverage: 67%
Expected cues: absolute, value, elastic, inelastic, revenue
Mark correct? [y/n/enter to accept estimate]

Saved quiz results.

Professor & Course Strategy Insights
From syllabus/materials: use the syllabus learning objectives as the answer checklist.
From student reviews (polyratings.dev): recurring student-reported patterns support frequent quiz practice.
Agent inference: missed quiz items should become spaced repetition prompts.
```

## Deliverable 5D: Final Exam Review Sheet

```text
Most Likely On The Exam: Cheat-Sheet Review

Very Likely Exam Material
- Price Elasticity Of Demand (100/100, high confidence)
  Why: appears in final review, homework, quizzes, lecture slides, and objectives.
  Be ready to: calculate elasticity, classify demand, and connect price changes to total revenue.
  Evidence: Final_Review.md :: Unit 3 Review

- Consumer Surplus (86.4/100, high confidence)
  Why: appears in review material and repeats across lecture, quiz, and homework files.
  Be ready to: define consumer surplus and calculate it from a demand graph.
  Evidence: Study_Guide.md :: Welfare Analysis

Possibly Testable Material
- Deadweight Loss (58.2/100, medium confidence)
  Why: appears in homework and lecture notes, but not strongly emphasized in review materials.
  Be ready to: explain why taxes or price controls can create inefficient lost surplus.
  Evidence: Homework_05.docx :: Tax Incidence

Final pass: cover the topic names, define each from memory, then solve or explain one exam-style
prompt for each very-likely topic.

Professor & Course Strategy Insights

From syllabus/materials
- Final exam is heavily weighted and cumulative.
- Learning objectives explicitly name elasticity, revenue interpretation, and welfare analysis.

From student reviews (polyratings.dev)
- Student-reported recurring pattern: lectures/slides and quizzes are important study signals.
- Student-reported recurring pitfall: students describe the course as difficult or confusing, so do not rely on passive rereading.

Agent inference
- Spend most review time on worked calculation patterns and active recall.
- Use the review sheet as a checklist, then do mixed quiz questions until weak topics improve.
```
