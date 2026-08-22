"""Unit tests strictly for the generation layer and formatting logic."""

from unittest.mock import MagicMock, patch
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from src.config import Settings
from src.generation.chain import CricketAdjudicationEngine, format_docs


def test_format_docs_empty():
    """Verify fallback text when no documents are returned."""
    assert format_docs([]) == "No relevant law context found."


def test_format_docs_with_metadata():
    """Verify document formatting structures law numbers and sections."""
    docs = [
        Document(
            page_content="Ball strikes helmet on ground.",
            metadata={"law_number": "28", "section": "28.3 Helmets"}
        ),
        Document(
            page_content="Non-striker leaving ground early.",
            metadata={"law_number": "38", "section": "38.3 Run Out"}
        ),
    ]
    formatted = format_docs(docs)
    assert "[Law 28: 28.3 Helmets]\nBall strikes helmet on ground." in formatted
    assert "[Law 38: 38.3 Run Out]\nNon-striker leaving ground early." in formatted
    assert "\n\n---\n\n" in formatted


@patch("src.generation.chain.CricketRetriever")
def test_engine_adjudicate_successful_call(mock_retriever_class):
    """Verify adjudication pipeline coordinates retriever and LLM chain invocation."""
    settings = Settings(
        openai_api_key="sk-test",
        pinecone_api_key="pc-test",
        pinecone_index_name="cricket-index",
        llm_model="gpt-4o",
    )

    # 1. Mock the retriever
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = [
        Document(
            page_content="Law 38.3: Non-striker liable to be run out before release.",
            metadata={"law_number": "38", "section": "38.3 Non-striker early"}
        )
    ]
    mock_retriever_class.return_value = mock_retriever

    # 2. Instantiate engine and replace LLM with a Fake Chat Model
    engine = CricketAdjudicationEngine(settings=settings)
    fake_response = "VERDICT: OUT. Law 38.3.1 allows dismissal before delivery stride ends."
    engine.llm = GenericFakeChatModel(messages=iter([fake_response]))
    
    # Rebuild LCEL chain with fake model
    engine.chain = engine.prompt | engine.llm | engine.chain.steps[-1]

    # 3. Adjudicate
    verdict, docs = engine.adjudicate("Can bowler run out non-striker?")

    assert len(docs) == 1
    assert "VERDICT: OUT" in verdict
    mock_retriever.retrieve.assert_called_once_with("Can bowler run out non-striker?", top_k=None)