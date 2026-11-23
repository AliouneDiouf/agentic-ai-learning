# AI Act RAG

Ask questions about the **EU AI Act** (Regulation (EU) 2024/1689) and get answers
taken from the official text, with the page they come from.

A retrieval-augmented generation (RAG) pipeline with LangChain, OpenAI embeddings
and Pinecone. It started as the plain-text RAG exercise of my LangChain course;
I adapted it to PDF documents, page-level citations and several source files.

## How it works

```
data/*.pdf ──pypdf──> one document per page (file name + page number)
                │
                ▼
   RecursiveCharacterTextSplitter (1000 chars, 150 overlap)
                │
                ▼
   OpenAI embeddings (text-embedding-3-small) ──> Pinecone index
                                                      │
question ──embedding──> top 4 chunks ─────────────────┘
                │
                ▼
   prompt: answer only from the chunks, cite file and page,
           say so when the answer is not there
                │
                ▼
             LLM answer
```

- **Page-level citations.** Each chunk keeps its file name and page number, and the
  prompt shows them to the model, so every answer can point to the page it comes from.
- **Scanned PDF check.** A PDF made of images gives almost no text; the ingestion stops
  with a clear message instead of indexing empty pages.
- **Idempotent ingestion.** Chunks get stable ids (`<file>-p<page>-<n>`): running the
  ingestion again overwrites the vectors instead of duplicating them.
- **Several documents.** Every PDF in `data/` is ingested into the same index.
- **Two implementations of the chain** in `main.py`: step by step, and with LCEL
  (`RunnablePassthrough.assign(...) | prompt | llm | parser`), compared with a raw LLM
  call that has no retrieval.

## Run it

1. Download the French text of the AI Act from
   [EUR-Lex](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/fra) (PDF) and save it as
   `data/ai_act_fr.pdf`. The PDF is not stored in this repository.
2. Copy `.env.example` to `.env` and fill in your OpenAI and Pinecone keys.
3. Install and run:

```bash
pip install -r requirements.txt
python create_index.py   # creates the Pinecone index (deletes it first if it exists)
python ingestion.py      # loads, splits, embeds and stores the PDF
python main.py           # asks a question with and without retrieval
```

Example questions:

- *Quelles pratiques d'intelligence artificielle sont interdites par le règlement ?*
- *Quelles sont les obligations des fournisseurs de systèmes d'IA à haut risque ?*

## Limits and next steps

The AI Act was amended in July 2026 by the *Digital Omnibus on AI*
(Regulation (EU) 2026/1744). With the 2024 text alone, some answers — dates of
application in particular — may be out of date.

- [ ] Add the 2026 amending regulation as a second source, and make the answer say
  which text each point comes from
- [ ] Evaluate retrieval and answers on a set of questions with known articles
- [ ] Add a chat interface

## Sources

Regulation (EU) 2024/1689 — © European Union, [EUR-Lex](https://eur-lex.europa.eu).
Reuse is authorised provided the source is acknowledged.
