"""Retrieval service to query Pinecone for relevant MCC Law clauses."""

from __future__ import annotations

import argparse
import json
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

from src.config import Settings, load_settings


class CricketRetriever:
    """Retrieve grounded law passages from Pinecone."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        if not self.settings.is_ready:
            raise ValueError(f"Missing required settings: {self.settings.missing_variables}")

        pc = Pinecone(api_key=self.settings.pinecone_api_key)
        self.index = pc.Index(self.settings.pinecone_index_name)
        self.embeddings = OpenAIEmbeddings(
            model=self.settings.embedding_model,
            openai_api_key=self.settings.openai_api_key,
        )

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filter_dict: dict | None = None,
    ) -> list[Document]:
        """Embed user query and fetch the top matching law documents from Pinecone."""
        k = top_k or self.settings.top_k
        query_vector = self.embeddings.embed_query(query)

        search_args = {
            "vector": query_vector,
            "top_k": k,
            "include_metadata": True,
        }
        if filter_dict:
            search_args["filter"] = filter_dict

        results = self.index.query(**search_args)

        retrieved_docs: list[Document] = []
        for match in results.matches:
            metadata = dict(match.metadata or {})
            content = metadata.pop("text", "")
            retrieved_docs.append(Document(page_content=content, metadata=metadata))

        return retrieved_docs


def main():
    parser = argparse.ArgumentParser(description="Query Pinecone for MCC Cricket Law clauses.")
    parser.add_argument("query", type=str, help="Search query or match scenario description")
    parser.add_argument("-k", "--top-k", type=int, default=3, help="Number of chunks to return (default: 3)")
    parser.add_argument("-l", "--law", type=str, default=None, help="Filter by specific Law number (e.g. 38)")
    parser.add_argument("--json-filter", type=str, default=None, help='Raw JSON filter string (e.g. \'{"law_number": {"$eq": "19"}}\')')

    args = parser.parse_args()

    filter_dict = None
    if args.law:
        filter_dict = {"law_number": {"$eq": str(args.law)}}
    elif args.json_filter:
        filter_dict = json.loads(args.json_filter)

    retriever = CricketRetriever()
    print(f"\n🔍 Querying: '{args.query}' (top_k={args.top_k}, filter={filter_dict})\n" + "=" * 60)

    docs = retriever.retrieve(query=args.query, top_k=args.top_k, filter_dict=filter_dict)

    if not docs:
        print("No matching clauses found.")
        return

    for i, doc in enumerate(docs, 1):
        law_no = doc.metadata.get("law_number", "N/A")
        section = doc.metadata.get("section", "N/A")
        title = doc.metadata.get("law_title", "")
        print(f"\n[{i}] Law {law_no}: {title} | Section: {section}")
        print("-" * 60)
        print(doc.page_content.strip())
        print("=" * 60)


if __name__ == "__main__":
    main()