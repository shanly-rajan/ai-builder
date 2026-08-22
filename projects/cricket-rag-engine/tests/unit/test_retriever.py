"""Unit tests strictly for the CricketRetriever component."""

import pytest
from unittest.mock import MagicMock, patch
from src.config import Settings
from src.retrieval.retriever import CricketRetriever


@pytest.fixture
def mock_settings():
    """Fixture providing ready test settings."""
    return Settings(
        openai_api_key="sk-test-openai",
        pinecone_api_key="pc-test-pinecone",
        pinecone_index_name="cricket-laws-index",
        embedding_dim=1536,
        top_k=3,
    )


@patch("src.retrieval.retriever.Pinecone")
@patch("src.retrieval.retriever.OpenAIEmbeddings")
def test_retriever_initialization_failure(mock_embeddings, mock_pinecone):
    """Verify that CricketRetriever raises ValueError if required settings are missing."""
    empty_settings = Settings(
        openai_api_key="",
        pinecone_api_key="",
        pinecone_index_name="",
    )
    with pytest.raises(ValueError) as excinfo:
        CricketRetriever(settings=empty_settings)
    
    assert "Missing required settings" in str(excinfo.value)


@patch("src.retrieval.retriever.Pinecone")
@patch("src.retrieval.retriever.OpenAIEmbeddings")
def test_retrieve_unpacks_matches_correctly(mock_embeddings, mock_pinecone, mock_settings):
    """Verify that search results unpack raw text into page_content and preserve custom metadata."""
    # 1. Mock OpenAI embedding output
    mock_embed_instance = MagicMock()
    mock_embed_instance.embed_query.return_value = [0.05] * 1536
    mock_embeddings.return_value = mock_embed_instance

    # 2. Mock Pinecone query return matches
    match_1 = MagicMock()
    match_1.metadata = {
        "law_number": "38",
        "law_title": "RUN OUT",
        "section": "38.3 Non-striker leaving ground early",
        "text": "The non-striker is liable to be Run out prior to delivery release.",
    }
    
    match_2 = MagicMock()
    match_2.metadata = {
        "law_number": "28",
        "law_title": "THE FIELDER",
        "section": "28.3 Protective helmets",
        "text": "5 penalty runs awarded if ball strikes helmet on ground.",
    }

    mock_index = MagicMock()
    mock_index.query.return_value = MagicMock(matches=[match_1, match_2])
    
    mock_pc = MagicMock()
    mock_pc.Index.return_value = mock_index
    mock_pinecone.return_value = mock_pc

    # 3. Instantiate and run retrieve
    retriever = CricketRetriever(settings=mock_settings)
    docs = retriever.retrieve(query="non striker leaving early")

    # 4. Verify embedding call and query arguments
    mock_embed_instance.embed_query.assert_called_once_with("non striker leaving early")
    mock_index.query.assert_called_once_with(
        vector=[0.05] * 1536,
        top_k=3,
        include_metadata=True,
    )

    # 5. Verify documents structure
    assert len(docs) == 2
    assert docs[0].page_content == "The non-striker is liable to be Run out prior to delivery release."
    assert docs[0].metadata["law_number"] == "38"
    assert "text" not in docs[0].metadata  # Ensure text is popped out of metadata


@patch("src.retrieval.retriever.Pinecone")
@patch("src.retrieval.retriever.OpenAIEmbeddings")
def test_retrieve_with_metadata_filter(mock_embeddings, mock_pinecone, mock_settings):
    """Verify that filter_dict is passed through to the Pinecone query invocation."""
    mock_embed_instance = MagicMock()
    mock_embed_instance.embed_query.return_value = [0.01] * 1536
    mock_embeddings.return_value = mock_embed_instance

    mock_index = MagicMock()
    mock_index.query.return_value = MagicMock(matches=[])
    mock_pc = MagicMock()
    mock_pc.Index.return_value = mock_index
    mock_pinecone.return_value = mock_pc

    retriever = CricketRetriever(settings=mock_settings)
    custom_filter = {"law_number": {"$eq": "19"}}
    
    docs = retriever.retrieve(query="boundary catch", top_k=5, filter_dict=custom_filter)

    assert len(docs) == 0
    mock_index.query.assert_called_once_with(
        vector=[0.01] * 1536,
        top_k=5,
        include_metadata=True,
        filter=custom_filter,
    )