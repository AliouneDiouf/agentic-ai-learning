"""Evaluate the civic exam assistant on the official exam questions.

The question file has no reference answers, so a stronger model acts as a judge:
for each question it reads the Livret du citoyen and the assistant's answer, and
decides whether the Livret covers the question and whether the answer is right.

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
    "correct": "Bonne réponse, appuyée par le Livret",
    "incorrect": "Le Livret contient la réponse, mais l'assistant se trompe",
    "missed": "Le Livret contient la réponse, mais l'assistant dit ne pas la trouver",
    "refused_ok": "Le Livret ne couvre pas la question, et l'assistant le dit",
    "hallucination": "Le Livret ne couvre pas la question, mais l'assistant répond quand même",
    "error": "Erreur pendant l'appel à l'API",
}


class Judgement(BaseModel):
    answer_in_livret: bool
    assistant_answered: bool
    correct: bool
    grounded: bool
    comment: str


JUDGE_PROMPT = f"""Tu évalues un assistant de révision pour l'examen civique français. \
L'assistant doit répondre uniquement à partir du Livret du citoyen ci-dessous.

On te donne une question de l'examen et la réponse de l'assistant. Remplis les champs :
- answer_in_livret : le Livret contient-il l'information qui permet de répondre à la question ?
- assistant_answered : l'assistant a-t-il donné une réponse, au lieu de dire que \
l'information ne figure pas dans le Livret ?
- correct : la réponse de l'assistant est-elle exacte selon le Livret ? \
(false s'il n'a pas répondu)
- grounded : tout ce qu'affirme l'assistant se trouve-t-il dans le Livret, \
sans information ajoutée de l'extérieur ? (true s'il n'a pas répondu)
- comment : une phrase qui justifie ton jugement, en citant le passage du Livret utile.

Sois strict : une réponse vague, incomplète ou qui ajoute des faits absents du Livret \
n'est pas correcte.

## Le Livret du citoyen
{livret}
"""


def load_questions(path: Path) -> list[dict]:
    """Load the question file, whether it is a list or a list wrapped in an object."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = next((value for value in data.values() if isinstance(value, list)), [])
    return [q for q in data if isinstance(q, dict) and q.get("question")]


def judge(question: str, answer: str, model: str) -> Judgement:
    messages = [
        {"role": "system", "content": JUDGE_PROMPT},
        {"role": "user", "content": f"Question : {question}\n\nRéponse de l'assistant : {answer}"},
    ]
    response = openai.chat.completions.parse(
        model=model, messages=messages, response_format=Judgement
    )
    return response.choices[0].message.parsed


def categorize(j: Judgement) -> str:
    if j.assistant_answered:
        if not j.answer_in_livret:
            return "hallucination"
        return "correct" if (j.correct and j.grounded) else "incorrect"
    return "missed" if j.answer_in_livret else "refused_ok"


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f} %" if whole else "n/a"


def write_report(rows: list[dict], path: Path, judge_model: str) -> str:
    counts = Counter(r["category"] for r in rows)
    total = len(rows)
    covered = counts["correct"] + counts["incorrect"] + counts["missed"]

    lines = [
        "# Evaluation report",
        "",
        f"- Questions evaluated: **{total}**",
        f"- Judge model: `{judge_model}`",
        f"- **Accuracy** (questions the Livret covers): **{pct(counts['correct'], covered)}**"
        f" ({counts['correct']}/{covered})",
        f"- Hallucination rate (answers to questions the Livret does not cover): "
        f"{pct(counts['hallucination'], total)}",
        f"- Livret coverage of the exam questions: {pct(covered, total)}",
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
        by_theme[r["thematique"] or "—"][r["category"]] += 1
    lines += [
        "",
        "## Accuracy by theme",
        "",
        "| Theme | Questions | Accuracy |",
        "|---|---|---|",
    ]
    for theme, c in sorted(by_theme.items()):
        theme_covered = c["correct"] + c["incorrect"] + c["missed"]
        lines.append(f"| {theme} | {sum(c.values())} | {pct(c['correct'], theme_covered)} |")

    report = "\n".join(lines) + "\n"
    path.write_text(report, encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--questions", default=HERE / "questions_cr.json", type=Path)
    parser.add_argument("--limit", type=int, default=None, help="evaluate only the first N questions")
    parser.add_argument("--judge-model", default="gpt-5.4")
    args = parser.parse_args()

    questions = load_questions(args.questions)[: args.limit]
    rows = []

    for i, q in enumerate(questions, 1):
        row = {
            "id": q.get("id", i),
            "thematique": q.get("thematique", ""),
            "question": q["question"],
        }
        try:
            answer = chat(q["question"], [])
            verdict = judge(q["question"], answer, args.judge_model)
            row.update(answer=answer, category=categorize(verdict), comment=verdict.comment)
        except Exception as exc:  # keep going: one failed call must not stop the run
            row.update(answer="", category="error", comment=str(exc))
        rows.append(row)
        print(f"[{i}/{len(questions)}] {row['category']:<13} {q['question'][:70]}")

    with open(HERE / "eval_results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "thematique", "question", "answer", "category", "comment"])
        writer.writeheader()
        writer.writerows(rows)

    print()
    print(write_report(rows, HERE / "eval_report.md", args.judge_model))
    print("Details: eval_results.csv — report: eval_report.md")


if __name__ == "__main__":
    main()
