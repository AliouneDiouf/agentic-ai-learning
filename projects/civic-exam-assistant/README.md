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

## Next steps

- [ ] Evaluate it on the 209 civic exam questions published on
  [data.gouv.fr](https://www.data.gouv.fr/datasets/examen-civique-cr/community-resources)
  and report the accuracy
- [ ] Add the Ministry's thematic sheets (Licence Etalab 2.0) as a second source
- [ ] Deploy on Hugging Face Spaces

## Status

Prototype built during week 1 of my agentic AI learning path.
