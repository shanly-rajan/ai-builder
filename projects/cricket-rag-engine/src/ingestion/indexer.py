"""Index parsed Law documents into Pinecone Serverless."""

from __future__ import annotations

import time
from pinecone import Pinecone, ServerlessSpec
from langchain_openai import OpenAIEmbeddings

from src.config import Settings, load_settings
from src.ingestion.parser import parse_mcc_laws


def index_documents(data_path: str = "data/sample/laws.txt", settings: Settings | None = None) -> int:
    """Read parsed documents, generate embeddings, and upsert to Pinecone."""
    cfg = settings or load_settings()
    if not cfg.is_ready:
        raise ValueError(f"Missing required environment variables: {cfg.missing_variables}")

    # 1. Initialize Pinecone client
    pc = Pinecone(api_key=cfg.pinecone_api_key)

    # 2. Create index if it does not exist
    existing_indexes = [idx.name for idx in pc.list_indexes()]
    if cfg.pinecone_index_name not in existing_indexes:
        print(f"Creating Pinecone index '{cfg.pinecone_index_name}'...")
        pc.create_index(
            name=cfg.pinecone_index_name,
            dimension=cfg.embedding_dim,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        while not pc.describe_index(cfg.pinecone_index_name).status["ready"]:
            time.sleep(1)

    index = pc.Index(cfg.pinecone_index_name)

    # 3. Parse data
    docs = parse_mcc_laws(data_path)
    embeddings = OpenAIEmbeddings(
        model=cfg.embedding_model,
        openai_api_key=cfg.openai_api_key,
    )

    # 4. Create vectors with metadata and upsert
    print(f"Embedding {len(docs)} chunks and upserting to Pinecone...")
    vectors = []
    for i, doc in enumerate(docs):
        embedding_val = embeddings.embed_query(doc.page_content)
        vectors.append({
            "id": f"law_chunk_{i}",
            "values": embedding_val,
            "metadata": {
                **doc.metadata,
                "text": doc.page_content,
            },
        })

    # Upsert in batches
    batch_size = 50
    for i in range(0, len(vectors), batch_size):
        index.upsert(vectors=vectors[i : i + batch_size])

    print(f"Successfully upserted {len(vectors)} vectors into '{cfg.pinecone_index_name}'.")
    return len(vectors)


if __name__ == "__main__":
    index_documents()