"""Adjudication generation chain using grounded MCC Law contexts."""

from __future__ import annotations

import argparse
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document

from src.config import Settings, load_settings
from src.retrieval.retriever import CricketRetriever

UMPIRE_SYSTEM_PROMPT = """You are the official Third Umpire and MCC Laws of Cricket adjudicator.
Deliver clear, definitive verdicts on match scenarios strictly grounded in the context clauses provided below.

Context clauses:
{context}

Adjudication Requirements:
1. State the Verdict directly: (e.g., OUT, NOT OUT, DEAD BALL, NO BALL, 5 PENALTY RUNS).
2. Cite the exact Law number, section, and sub-clause supporting the decision.
3. Detail the specific Umpire Action / Signal required (e.g., signal Dead Ball, award penalty runs).
4. If the context does not contain enough information to resolve the scenario under the official MCC Laws, output:
   "I cannot determine the ruling based on the official MCC Laws in the corpus."
5. Never invent or assume local tournament playing conditions (e.g., IPL/BBL) unless found in the context.
"""


def format_docs(docs: list[Document]) -> str:
    """Format retrieved documents into a clean readable string for prompt context."""
    if not docs:
        return "No relevant law context found."

    formatted = []
    for d in docs:
        law_ref = f"[Law {d.metadata.get('law_number', 'N/A')}: {d.metadata.get('section', 'N/A')}]"
        formatted.append(f"{law_ref}\n{d.page_content.strip()}")
    return "\n\n---\n\n".join(formatted)


class CricketAdjudicationEngine:
    """End-to-end engine tying retrieval to prompt-driven adjudication."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        if not self.settings.is_ready:
            raise ValueError(f"Missing required settings: {self.settings.missing_variables}")

        self.retriever = CricketRetriever(settings=self.settings)
        self.llm = ChatOpenAI(
            model=self.settings.llm_model,
            temperature=0.0,
            openai_api_key=self.settings.openai_api_key,
        )
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", UMPIRE_SYSTEM_PROMPT),
            ("human", "Match Scenario / Question: {question}\n\nContext:\n{context}"),
        ])
        self.chain = self.prompt | self.llm | StrOutputParser()

    def adjudicate(self, query: str, top_k: int | None = None) -> tuple[str, list[Document]]:
        """Retrieve relevant context and generate the official grounded adjudication."""
        docs = self.retriever.retrieve(query, top_k=top_k)
        context = format_docs(docs)
        verdict = self.chain.invoke({"question": query, "context": context})
        return verdict, docs


def main():
    parser = argparse.ArgumentParser(description="Adjudicate match scenarios using the MCC Laws RAG chain.")
    parser.add_argument("scenario", type=str, help="Match scenario or rule question to adjudicate")
    parser.add_argument("-k", "--top-k", type=int, default=None, help="Number of retrieved chunks")

    args = parser.parse_args()

    engine = CricketAdjudicationEngine()
    print(f"\n⚖️ Adjudicating Scenario: '{args.scenario}'\n" + "=" * 60)

    verdict, docs = engine.adjudicate(query=args.scenario, top_k=args.top_k)

    print("\n[VERDICT & ADJUDICATION]")
    print(verdict)
    print("\n" + "=" * 60)
    print(f"[RETRIEVED CITATIONS: {len(docs)} CLAUSES]")
    for i, doc in enumerate(docs, 1):
        print(f"[{i}] {doc.metadata.get('section', 'Law Clause')}")


if __name__ == "__main__":
    main()