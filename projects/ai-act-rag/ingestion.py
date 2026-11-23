"""Ingest every PDF of the data/ folder into a Pinecone index.

Each page keeps its file name and page number in the metadata,
so that the answers can cite their source.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

load_dotenv()

DATA_DIR = Path(__file__).parent / "data"
EMBEDDING_MODEL = "text-embedding-3-small"  # 1536 dimensions, as in create_index.py
MIN_CHARS_PER_PAGE = 200  # below this, the PDF is probably scanned (images, not text)


def load_pdf(path: Path) -> list[Document]:
    """One Document per page, with the file name and the page number (from 1)."""
    reader = PdfReader(path)
    pages = [
        Document(
            page_content=page.extract_text() or "",
            metadata={"source": path.name, "page": number},
        )
        for number, page in enumerate(reader.pages, 1)
    ]
    chars = sum(len(p.page_content) for p in pages)
    if chars < MIN_CHARS_PER_PAGE * len(pages):
        raise SystemExit(
            f"{path.name}: only {chars} characters for {len(pages)} pages. "
            "The PDF probably holds scanned images: run OCR first."
        )
    return pages


def split(pages: list[Document]) -> list[Document]:
    # Tries paragraphs first, then lines, then sentences, so that a chunk
    # never exceeds chunk_size. The overlap keeps the context between two chunks.
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    return splitter.split_documents(pages)


if __name__ == "__main__":
    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDF in {DATA_DIR}. Download one first (see README).")

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = PineconeVectorStore(index_name=os.environ["INDEX_NAME"], embedding=embeddings)

    for pdf in pdfs:
        pages = load_pdf(pdf)
        chunks = split(pages)
        # Stable ids: running the ingestion twice overwrites the vectors instead of duplicating them
        ids = [f"{pdf.stem}-p{c.metadata['page']}-{i}" for i, c in enumerate(chunks)]
        print(f"{pdf.name}: {len(pages)} pages -> {len(chunks)} chunks, ingesting...")
        vectorstore.add_documents(chunks, ids=ids)

    print("finish")
