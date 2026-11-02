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
Livret du citoyen (PDF, scanned) ──OCR──> livret.txt ──> system prompt
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

   The PDF stores its 83 pages as images: `pypdf` extracts fewer than 2,000 characters.
   Convert it to text with OCR (Poppler and Tesseract with French data), which gives
   about 150,000 characters with a `--- Page N ---` marker before each page:

   ```bash
   pdftoppm -r 300 -gray -png livret.pdf page
   for f in page-*.png; do tesseract "$f" "${f%.png}" -l fra; done
   python - <<'PY'
   import re, pathlib
   files = sorted(pathlib.Path('.').glob('page-*.txt'), key=lambda p: int(re.findall(r'\d+', p.stem)[0]))
   text = "\n\n".join(f"--- Page {int(re.findall(r'\d+', p.stem)[0])} ---\n{p.read_text(encoding='utf-8').strip()}" for p in files)
   pathlib.Path('livret.txt').write_text(text, encoding='utf-8')
   PY
   ```

   `app.py` reads `livret.txt`, and refuses to start if the text is nearly empty.
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
compares the assistant's answer with them, checks that it comes from the Livret, and
accepts another answer when it is also right according to the Livret (several answers
are often valid, e.g. when the question asks for an example). Each answer falls into one
category:

| Category | Meaning |
|---|---|
| `correct` | Right answer, taken from the Livret |
| `correct_outside` | Right answer, but not in the Livret (outside knowledge) |
| `valid_other` | Right according to the Livret, but different from the reference |
| `incorrect` | Wrong answer, or an answer to a different question |
| `missed` | The Livret has the answer, the assistant says it cannot find it |
| `not_in_livret` | The Livret does not cover the question, and the assistant says so |

The real exam is multiple choice, but the file only lists the right answers, so the
assistant gets each question without the choices — a harder setting than the exam.

### Dev and test sets

As with any model, tuning the prompt on the questions used for the final score would
overfit it. The questions are split once: **1 in 5 goes to a dev set (42 questions)**,
used to read errors and improve the prompt; **the other 167 form the test set**, run only
to report scores.

### Prompt versions

- **v1** — the original prompt.
- **v2** — adds a section on answering the exact question asked, giving complete answers
  with the Livret's own key terms, and picking the most direct passage. It targets the two
  failure modes seen on the dev set: answering a neighbouring question, and right but
  incomplete answers.

### Run it

Download the JSON file from
[data.gouv.fr](https://www.data.gouv.fr/datasets/examen-civique-cr/community-resources)
(209 questions in 5 themes for the resident card, with suggested correct answers;
Licence Ouverte 2.0, source: qcmexamencivique.fr), save it as `questions_cr.json` in
this folder, then:

```bash
python evaluate.py --split dev  --prompt v1   # study errors
python evaluate.py --split test --prompt v1   # baseline score
python evaluate.py --split dev  --prompt v2   # check the fix
python evaluate.py --split test --prompt v2   # final score
```

Each run writes `eval_<prompt>_<split>.md` (summary) and `.csv` (every answer and verdict).

The judge is a model too: check a sample of its verdicts by hand before trusting the score.

### Results

Accuracy (right answers, reference or other valid answer), judge `gpt-5.4`:

| Prompt | Dev (42) | Test (167) | Wrong answers (test) |
|---|---|---|---|
| v1 | 83.3 % | 83.8 % | 10.2 % |
| v2 | 83.3 % | **85.6 %** | 9.0 % |

What the numbers say:

- **The assistant answers about 85 % of the exam questions correctly**, without seeing
  the multiple-choice options.
- **v2 is not a significant improvement.** Comparing the two prompts question by
  question on the test set, v2 fixes 5 answers and breaks 2 (exact McNemar test,
  p = 0.45); on the dev set it fixes 2 and breaks 2. v2 stays the default, but prompt
  wording has reached a plateau.
- **The Livret does not cover everything the exam asks.** By the judge's count it holds
  the answer to about 89 % of the test questions, and the weakest theme, *Vivre dans la
  société française*, is at about 60 %. About one question in ten cannot be answered
  from the Livret at all, which caps what a Livret-only assistant can reach — so the next
  lever is a second source rather than further prompt tweaks.
- A first run scored 20 %: it revealed that the official PDF holds images and that the
  assistant had been given an almost empty text. The OCR step and the start-up check in
  `app.py` come from that finding.

## Next steps

- [x] Evaluate both prompt versions on dev and test sets
- [ ] Add the Ministry's thematic sheets (Licence Etalab 2.0) as a second source,
  to cover the questions the Livret misses
- [ ] Deploy on Hugging Face Spaces

## Status

Prototype built during week 1 of my agentic AI learning path.
