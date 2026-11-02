"""Evaluate the civic exam assistant on the official exam questions.

The question file gives, for each question, one or more correct answers.
A stronger model acts as a judge: it compares the assistant's answer with these
reference answers and checks that the answer comes from the Livret du citoyen.

Usage:
    python evaluate.py --limit 20          # quick, cheap first run
    python evaluate.py                      # all questions
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from pydantic import BaseModel

from app import chat, livret, openai

HERE = Path(__file__).parent

CATEGORIES = {
    "correct": "Bonne réponse, tirée du Livret",
    "correct_outside": "Bonne réponse, mais absente du Livret (connaissance extérieure)",
    "incorrect": "Mauvaise réponse",
    "missed": "Le Livret contient la réponse, mais l'assistant dit ne pas la trouver",
    "not_in_livret": "Le Livret ne couvre pas la question, et l'assistant le dit",
    "error": "Erreur pendant l'appel à l'API",
}


class Judgement(BaseModel):
    answer_in_livret: bool
    assistant_answered: bool
    matches_reference: bool
    grounded: bool
    comment: str


JUDGE_PROMPT = f"""Tu évalues un assistant de révision pour l'examen civique français. \
L'assistant doit répondre uniquement à partir du Livret du citoyen ci-dessous.

On te donne une question de l'examen, les réponses correctes de référence \
(une seule suffit) et la réponse de l'assistant. Remplis les champs :
- answer_in_livret : le Livret contient-il l'information qui permet de répondre correctement ?
- assistant_answered : l'assistant a-t-il donné une réponse, au lieu de dire que \
l'information ne figure pas dans le Livret ?
- matches_reference : la réponse de l'assistant correspond-elle à au moins une des \
réponses de référence, sans affirmation fausse ? (false s'il n'a pas répondu)
- grounded : ce qu'affirme l'assistant se trouve-t-il dans le Livret, sans information \
ajoutée de l'extérieur ? (true s'il n'a pas répondu)
- comment : une phrase qui justifie ton jugement.

Sois strict : une réponse vague, ou qui contient une erreur à côté d'une bonne réponse, \
ne correspond pas à la référence.

## Le Livret du citoyen
{livret}
"""


def load_questions(path: Path) -> list[dict]:
    """Load questions as dicts with id, theme, question and reference answers.

    Accepts the data.gouv.fr layout ({"data": [{"theme", "questions": [...]}]})
    as well as a flat list of questions.
    """
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        data = data.get("data", [])

    questions = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if "questions" in item:  # a theme holding its questions
            theme = item.get("theme", "")
            for q in item["questions"]:
                questions.append({**q, "theme": q.get("theme", theme)})
        elif "question" in item:
            questions.append(item)

    return [
        {
            "id": q.get("id", i),
            "theme": q.get("theme") or q.get("thematique", ""),
            "question": q["question"],
            "references": q.get("suggested_answers", []),
        }
        for i, q in enumerate(questions, 1)
        if q.get("question")
    ]


def ask_assistant(question: str) -> str:
    # The real exam is a multiple-choice test, but the file only lists the right answers,
    # so the assistant gets the question without the choices.
    message = (
        "Question de l'examen civique (les propositions ne sont pas fournies, "
        f"donne directement la bonne réponse) : {question}"
    )
    return chat(message, [])


def judge(question: str, references: list[str], answer: str, model: str) -> Judgement:
    refs = "\n".join(f"- {r}" for r in references) or "- (aucune)"
    messages = [
        {"role": "system", "content": JUDGE_PROMPT},
        {
            "role": "user",
            "content": f"Question : {question}\n\nRéponses de référence :\n{refs}\n\n"
            f"Réponse de l'assistant : {answer}",
        },
    ]
    response = openai.chat.completions.parse(
        model=model, messages=messages, response_format=Judgement
    )
    return response.choices[0].message.parsed


def categorize(j: Judgement) -> str:
    if j.assistant_answered:
        if not j.matches_reference:
            return "incorrect"
        return "correct" if j.grounded else "correct_outside"
    return "missed" if j.answer_in_livret else "not_in_livret"


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f} %" if whole else "n/a"


def write_report(rows: list[dict], path: Path, judge_model: str) -> str:
    counts = Counter(r["category"] for r in rows)
    total = len(rows)
    right = counts["correct"] + counts["correct_outside"]
    covered = sum(1 for r in rows if r["answer_in_livret"] == "yes")

    lines = [
        "# Evaluation report",
        "",
        f"- Questions evaluated: **{total}**",
        f"- Judge model: `{judge_model}`",
        f"- **Accuracy**: **{pct(right, total)}** ({right}/{total} answers match the reference)",
        f"- Accuracy using the Livret only: {pct(counts['correct'], total)}",
        f"- Questions the Livret covers (judge's view): {pct(covered, total)}",
        "",
        "## Results by category",
        "",
        "| Category | Meaning | Count | Share |",
        "|---|---|---|---|",
    ]
    for cat, meaning in CATEGORIES.items():
        lines.append(f"| `{cat}` | {meaning} | {counts[cat]} | {pct(counts[cat], total)} |")

    by_theme = defaultdict(Counter)
    for r in rows:
        by_theme[r["theme"] or "—"][r["category"]] += 1
    lines += ["", "## Accuracy by theme", "", "| Theme | Questions | Accuracy |", "|---|---|---|"]
    for theme, c in sorted(by_theme.items()):
        n = sum(c.values())
        lines.append(f"| {theme} | {n} | {pct(c['correct'] + c['correct_outside'], n)} |")

    report = "\n".join(lines) + "\n"
    path.write_text(report, encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--questions", default=HERE / "questions_cr.json", type=Path)
    parser.add_argument("--limit", type=int, default=None, help="evaluate only the first N questions")
    parser.add_argument("--judge-model", default="gpt-5.4")
    args = parser.parse_args()

    questions = load_questions(args.questions)
    if not questions:
        raise SystemExit(f"No questions found in {args.questions}. Check the file format.")
    if args.limit and args.limit < len(questions):
        # Spread the sample over the whole file so every theme is represented
        step = len(questions) // args.limit
        questions = questions[::step][: args.limit]

    rows = []
    for i, q in enumerate(questions, 1):
        row = {
            "id": q["id"],
            "theme": q["theme"],
            "question": q["question"],
            "references": " | ".join(q["references"]),
        }
        try:
            answer = ask_assistant(q["question"])
            verdict = judge(q["question"], q["references"], answer, args.judge_model)
            row.update(
                answer=answer,
                category=categorize(verdict),
                answer_in_livret="yes" if verdict.answer_in_livret else "no",
                comment=verdict.comment,
            )
        except Exception as exc:  # keep going: one failed call must not stop the run
            row.update(answer="", category="error", answer_in_livret="", comment=str(exc))
        rows.append(row)
        print(f"[{i}/{len(questions)}] {row['category']:<15} {q['question'][:65]}")

    fields = ["id", "theme", "question", "references", "answer", "category", "answer_in_livret", "comment"]
    with open(HERE / "eval_results.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print()
    print(write_report(rows, HERE / "eval_report.md", args.judge_model))
    print("Details: eval_results.csv — report: eval_report.md")


if __name__ == "__main__":
    main()
