"""Civic exam assistant: answers questions about the French civic exam
using only the official "Livret du citoyen"."""

from pathlib import Path

import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

MODEL = "gpt-5.4-mini"
LIVRET_PATH = Path(__file__).parent / "livret.pdf"

load_dotenv(override=True)  # loads OPENAI_API_KEY from .env
openai = OpenAI()


def load_livret(path: Path) -> str:
    """Extract the text of the Livret du citoyen PDF."""
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text
    return text


livret = load_livret(LIVRET_PATH)

system_prompt = f"""Tu es un assistant de révision pour l'examen civique français. \
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
- Termine en indiquant la partie du Livret d'où vient l'information.
- Écris en français simple, avec des phrases courtes. Beaucoup de personnes \
qui te consultent n'ont pas le français comme langue maternelle.
- Si la personne écrit dans une autre langue, réponds dans sa langue, \
mais garde les termes officiels en français (par exemple « laïcité »).

## Mode entraînement
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


def to_text(content) -> str:
    """Convert a Gradio message content into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


def chat(message, history):
    # Keep only role and text: the OpenAI API rejects Gradio's extra fields
    clean_history = [{"role": h["role"], "content": to_text(h["content"])} for h in history]

    messages = (
        [{"role": "system", "content": system_prompt}]
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
