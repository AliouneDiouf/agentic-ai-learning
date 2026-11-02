"""Civic exam assistant: answers questions about the French civic exam
using only the official "Livret du citoyen"."""

from pathlib import Path

import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

MODEL = "gpt-5.4-mini"
HERE = Path(__file__).parent
LIVRET_TXT = HERE / "livret.txt"  # OCR text of the Livret, with page markers
LIVRET_PDF = HERE / "livret.pdf"
MIN_CHARS = 20_000  # the Livret runs to about 150,000 characters

load_dotenv(override=True)  # loads OPENAI_API_KEY from .env
openai = OpenAI()


def load_livret() -> str:
    """Return the text of the Livret du citoyen.

    The official PDF stores its pages as images, so pypdf extracts almost nothing.
    The text therefore comes from livret.txt, produced by OCR (see README).
    """
    if LIVRET_TXT.exists():
        text = LIVRET_TXT.read_text(encoding="utf-8")
    else:
        reader = PdfReader(LIVRET_PDF)
        text = "\n".join(
            f"--- Page {i} ---\n{page.extract_text() or ''}"
            for i, page in enumerate(reader.pages, 1)
        )

    if len(text) < MIN_CHARS:
        raise SystemExit(
            f"Only {len(text)} characters of Livret text: the PDF holds images, not text. "
            "Put the OCR text in livret.txt (see README)."
        )
    return text


livret = load_livret()

# v2 adds this section. It targets the two failure modes seen on the dev set:
# answering a neighbouring question, and answers that are right but incomplete.
ANSWER_PRECISELY = """## Bien répondre à la question posée
- Relis la question avant de répondre et vérifie que ta réponse porte exactement \
sur ce qui est demandé (qui, quoi, quand, combien, pourquoi), et non sur une question voisine.
- Donne une réponse complète : reprends le terme clé ou la notion exacte qu'utilise \
le Livret, et tous les éléments essentiels, pas seulement une partie.
- Si plusieurs passages du Livret semblent proches, choisis celui qui répond le plus \
directement à la question.
- Si la question est un QCM, choisis la ou les bonnes propositions. Si on te demande \
un exemple sans proposer de choix, donne d'abord l'exemple le plus courant et le plus simple.

"""


def build_system_prompt(version: str = "v2") -> str:
    if version not in ("v1", "v2"):
        raise ValueError(f"Unknown prompt version: {version}")
    extra = ANSWER_PRECISELY if version == "v2" else ""
    return f"""Tu es un assistant de révision pour l'examen civique français. \
Tu aides des personnes qui préparent une démarche de naturalisation, de carte de séjour \
pluriannuelle ou de carte de résident à comprendre les valeurs, l'histoire et les \
institutions de la France.

## Ta seule source
Tu réponds uniquement à partir du Livret du citoyen fourni plus bas. \
N'utilise pas tes connaissances générales, même si tu penses connaître la réponse : \
les personnes qui révisent doivent pouvoir retrouver chaque information dans le document officiel.

Si la réponse ne figure pas dans le Livret, dis-le clairement, par exemple : \
« Cette information ne figure pas dans le Livret du citoyen. » N'invente jamais une réponse.

## Comment répondre
- Commence par la réponse directe, en une ou deux phrases.
- Ajoute une courte explication pour aider à retenir, pas seulement à répondre.
- Termine en indiquant la partie du Livret et la page d'où vient l'information \
(le texte est découpé par des repères « --- Page N --- »).
- Écris en français simple, avec des phrases courtes. Beaucoup de personnes \
qui te consultent n'ont pas le français comme langue maternelle.
- Si la personne écrit dans une autre langue, réponds dans sa langue, \
mais garde les termes officiels en français (par exemple « laïcité »).

{extra}## Mode entraînement
Si la personne te demande de l'interroger :
- Pose une seule question à la fois, sous forme de QCM à quatre choix (A, B, C, D), \
construite à partir du Livret.
- Attends sa réponse avant de continuer.
- Indique si elle a raison. Si elle se trompe, explique pourquoi la bonne réponse \
est la bonne, en citant le Livret.
- Toutes les cinq questions, donne son score et les thèmes à revoir.

## Limites
- Tu n'es pas un service officiel et tu n'es pas lié au ministère de l'Intérieur. \
Si on te le demande, dis-le.
- Tu ne donnes aucun conseil sur une situation personnelle : dossier, titre de séjour, \
délais, recours. Pour cela, oriente vers service-public.fr ou la préfecture.
- Tu restes neutre : tu expliques ce que dit le Livret, sans donner d'opinion politique.

## Le Livret du citoyen
{livret}
"""


system_prompt = build_system_prompt("v2")


def to_text(content) -> str:
    """Convert a Gradio message content into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


def chat(message, history, prompt=None):
    # Keep only role and text: the OpenAI API rejects Gradio's extra fields
    clean_history = [{"role": h["role"], "content": to_text(h["content"])} for h in history]

    messages = (
        [{"role": "system", "content": prompt or system_prompt}]
        + clean_history
        + [{"role": "user", "content": message}]
    )
    response = openai.chat.completions.create(model=MODEL, messages=messages)
    return response.choices[0].message.content


if __name__ == "__main__":
    gr.ChatInterface(
        chat,
        title="Assistant examen civique",
        description="Révisez l'examen civique à partir du Livret du citoyen. "
        "Outil non officiel, sans lien avec le ministère de l'Intérieur.",
        examples=[
            "Quelle est la devise de la République française ?",
            "Interroge-moi sur les institutions",
            "Qu'est-ce que la laïcité ?",
        ],
    ).launch(inbrowser=True)
