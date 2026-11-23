"""Create (or recreate) the Pinecone index that stores the chunks."""

import os

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

load_dotenv()

if __name__ == "__main__":
    pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
    index_name = os.environ["INDEX_NAME"]

    if pc.has_index(index_name):
        print(f"Index {index_name} already exists and will be deleted.")
        pc.delete_index(index_name)

    pc.create_index(
        name=index_name,
        vector_type="dense",
        dimension=1536,  # text-embedding-3-small
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
    print(f"Index {index_name} created.")
