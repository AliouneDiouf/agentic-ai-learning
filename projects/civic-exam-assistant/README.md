# Civic Exam Assistant

A chat assistant that helps people prepare for the French **examen civique** —
the multiple-choice civics test required since 2026 for naturalisation, the
multi-year residence permit and the resident card.

It answers **only from the official *Livret du citoyen***, says so when the answer
is not in the document, and can quiz the user one question at a time.

> Unofficial tool. Not affiliated with the French Ministry of the Interior.

## What it does

- **Grounded answers.** The full text of the *Livret du citoyen* is placed in the
  system prompt; the model is instructed to answer from it alone and to point to
  the section the answer comes from.
- **Quiz mode.** Ask *« Interroge-moi »*: it asks one four-option question at a time,
  corrects the answer with a reference to the Livret, and gives a score every five
  questions.
- **Plain French.** Short sentences for users whose first language is not French;
  replies in the user's language when they write in another one.
- **Guardrails.** No advice on personal immigration cases (redirects to
  service-public.fr or the prefecture), no political opinions, no invented answers.

## How it works

```
Livret du citoyen (PDF) ──pypdf──> text ──> system prompt
                                              │
        user message + chat history ──────────┤
                                              ▼
                                   OpenAI chat completion
                                              │
                                              ▼
                                       Gradio chat UI
```

The document is short enough to fit in the model's context, so no retrieval step
is needed. The system prompt stays first and identical across calls, which lets
the API reuse its prompt cache.

## Run it

1. Download the official PDF and save it as `livret.pdf` in this folder:
   [Livret du citoyen 2026](https://www.immigration.interieur.gouv.fr/sites/dgef/files/medias/documents/2026-07/LIVRET-DU-CITOYEN-2026.pdf)
2. Put your key in a `.env` file: `OPENAI_API_KEY=sk-...`
3. Install and launch:

```bash
pip install -r requirements.txt
python app.py
```

## Evaluation

`evaluate.py` runs the assistant on the 209 civic exam questions and scores every answer
with a stronger model acting as a judge (**LLM-as-a-judge**, with structured output).

The question file lists, for each question, one or more correct answers. The judge
compares the assistant's answer with them, and also checks whether the answer comes
from the Livret. Each answer falls into one category:

| Category | Meaning |
|---|---|
| `correct` | Right answer, taken from the Livret |
| `correct_outside` | Right answer, but not in the Livret (outside knowledge) |
| `incorrect` | Wrong answer |
| `missed` | The Livret has the answer, the assistant says it cannot find it |
| `not_in_livret` | The Livret does not cover the question, and the assistant says so |

The report gives the **accuracy** against the reference answers, the accuracy using the
Livret only, and how much of the exam the Livret covers, overall and by theme.

The real exam is multiple choice, but the file only lists the right answers, so the
assistant gets each question without the choices — a harder setting than the exam.

To run it, download the JSON file from
[data.gouv.fr](https://www.data.gouv.fr/datasets/examen-civique-cr/community-resources)
(209 questions in 5 themes for the resident card, with suggested correct answers;
Licence Ouverte 2.0, source: qcmexamencivique.fr),
save it as `questions_cr.json` in this folder, then:

```bash
python evaluate.py --limit 20   # quick first run
python evaluate.py              # all questions
```

It writes `eval_report.md` (summary) and `eval_results.csv` (every answer and verdict).

The judge is a model too: check a sample of its verdicts by hand before trusting the score.

## Next steps

- [ ] Run the full evaluation and publish `eval_report.md`
- [ ] Add the Ministry's thematic sheets (Licence Etalab 2.0) as a second source
- [ ] Deploy on Hugging Face Spaces

## Status

Prototype built during week 1 of my agentic AI learning path.
