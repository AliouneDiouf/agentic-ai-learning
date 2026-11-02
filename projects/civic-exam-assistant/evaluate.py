"""Evaluate the civic exam assistant on the official exam questions.

The question file gives, for each question, one or more correct answers.
A stronger model acts as a judge: it compares the assistant's answer with these
reference answers and checks that the answer comes from the Livret du citoyen.

The 209 questions are split once and for all into a dev set (1 in 5, used to study
errors and improve the prompt) and a test set (the rest, only for the final score).

Usage:
    python evaluate.py --split dev --prompt v1     # study errors
    python evaluate.py --split test --prompt v2    # final score, look at the number only
    python evaluate.py --split dev --limit 10      # quick check
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from pydantic import BaseModel

from app import build_system_prompt, chat, livret, openai

HERE = Path(__file__).parent

CATEGORIES = {
    "correct": "Bonne réponse, tirée du Livret",
    "correct_outside": "Bonne réponse, mais absente du Livret (connaissance extérieure)",
    "valid_other": "Réponse juste selon le Livret, mais différente de la référence",
    "incorrect": "Mauvaise réponse, ou réponse à côté de la question",
    "missed": "Le Livret contient la réponse, mais l'assistant dit ne pas la trouver",
    "not_in_livret": "Le Livret ne couvre pas la question, et l'assistant le dit",
    "error": "Erreur pendant l'appel à l'API",
}


class Judgement(BaseModel):
    answer_in_livret: bool
    assistant_answered: bool
    matches_reference: bool
    valid_per_livret: bool
    grounded: bool
    comment: str


JUDGE_PROMPT = f"""Tu évalues un assistant de révision pour l'examen civique français. \
L'assistant doit répondre uniquement à partir du Livret du citoyen ci-dessous.

On te donne une question de l'examen, les réponses correctes de référence \
(une seule suffit) et la réponse de l'assistant. Remplis les champs :
- answer_in_livret : le Livret contient-il l'information qui permet de répondre correctement ?
- assistant_answered : l'assistant a-t-il donné une réponse, au lieu de dire que \
l'information ne figure pas dans le Livret ?
- matches_reference : la réponse principale de l'assistant correspond-elle à au moins \
une des réponses de référence, avec ses éléments essentiels et sans affirmation fausse ? \
(false s'il n'a pas répondu)
- valid_per_livret : si matches_reference est false, la réponse répond-elle quand même \
correctement à la question posée, selon le Livret ? C'est le cas lorsque plusieurs réponses \
justes sont possibles, par exemple quand la question demande un exemple. \
false si la réponse porte sur une autre question, est fausse ou incomplète.
- grounded : les faits affirmés par l'assistant figurent-ils dans le Livret ? \
Une reformulation, un résumé ou une phrase de conclusion ne posent pas de problème ; \
mets false seulement si un fait important est absent du Livret ou le contredit. \
(true s'il n'a pas répondu)
- comment : une phrase qui justifie ton jugement.

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


def split_questions(questions: list[dict], split: str) -> list[dict]:
    """Fixed split: every 5th question goes to dev, the others to test."""
    if split == "all":
        return questions
    in_dev = [i % 5 == 0 for i in range(len(questions))]
    keep = in_dev if split == "dev" else [not d for d in in_dev]
    return [q for q, k in zip(questions, keep) if k]


def ask_assistant(question: str, prompt: str) -> str:
    # The real exam is a multiple-choice test, but the file only lists the right answers,
    # so the assistant gets the question without the choices.
    message = (
        "Question de l'examen civique (les propositions ne sont pas fournies, "
        f"donne directement la bonne réponse) : {question}"
    )
    return chat(message, [], prompt=prompt)


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
        if j.matches_reference:
            return "correct" if j.grounded else "correct_outside"
        return "valid_other" if j.valid_per_livret else "incorrect"
    return "missed" if j.answer_in_livret else "not_in_livret"


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f} %" if whole else "n/a"


def write_report(rows: list[dict], path: Path, judge_model: str, prompt: str, split: str) -> str:
    counts = Counter(r["category"] for r in rows)
    total = len(rows)
    matches = counts["correct"] + counts["correct_outside"]
    accepted = matches + counts["valid_other"]
    covered = sum(1 for r in rows if r["answer_in_livret"] == "yes")

    lines = [
        f"# Evaluation report — prompt {prompt}, {split} set",
        "",
        f"- Questions evaluated: **{total}**",
        f"- Judge model: `{judge_model}`",
        f"- **Accuracy** (right answer, reference or other valid answer): "
        f"**{pct(accepted, total)}** ({accepted}/{total})",
        f"- Strict accuracy (matches the reference): {pct(matches, total)} ({matches}/{total})",
        f"- Wrong answers: {pct(counts['incorrect'], total)} ({counts['incorrect']}/{total})",
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
        ok = c["correct"] + c["correct_outside"] + c["valid_other"]
        lines.append(f"| {theme} | {n} | {pct(ok, n)} |")

    report = "\n".join(lines) + "\n"
    path.write_text(report, encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--questions", default=HERE / "questions_cr.json", type=Path)
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--prompt", choices=["v1", "v2"], default="v2")
    parser.add_argument("--limit", type=int, default=None, help="evaluate only N questions")
    parser.add_argument("--judge-model", default="gpt-5.4")
    args = parser.parse_args()

    questions = load_questions(args.questions)
    if not questions:
        raise SystemExit(f"No questions found in {args.questions}. Check the file format.")
    questions = split_questions(questions, args.split)
    if args.limit and args.limit < len(questions):
        # Spread the sample over the whole set so every theme is represented
        step = len(questions) // args.limit
        questions = questions[::step][: args.limit]

    prompt = build_system_prompt(args.prompt)
    print(f"Prompt {args.prompt}, {args.split} set: {len(questions)} questions\n")

    rows = []
    for i, q in enumerate(questions, 1):
        row = {
            "id": q["id"],
            "theme": q["theme"],
            "question": q["question"],
            "references": " | ".join(q["references"]),
        }
        try:
            answer = ask_assistant(q["question"], prompt)
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

    stem = f"eval_{args.prompt}_{args.split}"
    fields = ["id", "theme", "question", "references", "answer", "category", "answer_in_livret", "comment"]
    with open(HERE / f"{stem}.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print()
    print(write_report(rows, HERE / f"{stem}.md", args.judge_model, args.prompt, args.split))
    print(f"Details: {stem}.csv — report: {stem}.md")


if __name__ == "__main__":
    main()
