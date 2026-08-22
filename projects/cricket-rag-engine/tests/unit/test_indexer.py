"""Unit tests for the Pinecone indexer logic using mocks."""

from unittest.mock import MagicMock, patch
from langchain_core.documents import Document
from src.config import Settings
from src.ingestion.indexer import index_documents


@patch("src.ingestion.indexer.Pinecone")
@patch("src.ingestion.indexer.OpenAIEmbeddings")
@patch("src.ingestion.indexer.parse_mcc_laws")
def test_index_documents_success(mock_parse, mock_embeddings_class, mock_pinecone_class, tmp_path):
    """Verify index creation check, embedding generation, and upsert payload structure."""
    # 1. Setup mock test settings
    test_settings = Settings(
        openai_api_key="sk-test-key",
        pinecone_api_key="pc-test-key",
        pinecone_index_name="test-cricket-index",
    )

    # 2. Mock parsed documents
    sample_docs = [
        Document(
            page_content="Law 38.1 Out Run out",
            metadata={"law_number": "38", "section": "38.1 Out Run out", "source": "MCC Laws"}
        ),
        Document(
            page_content="Law 28.3 Ball hitting helmet",
            metadata={"law_number": "28", "section": "28.3 Protective helmets", "source": "MCC Laws"}
        ),
    ]
    mock_parse.return_value = sample_docs

    # 3. Mock embeddings generator
    mock_embed_instance = MagicMock()
    mock_embed_instance.embed_query.return_value = [0.1] * 1536
    mock_embeddings_class.return_value = mock_embed_instance

    # 4. Mock Pinecone client and index operations
    mock_pc_instance = MagicMock()
    mock_index_instance = MagicMock()
    
    # Simulate that the index already exists in pc.list_indexes()
    mock_existing_index = MagicMock()
    mock_existing_index.name = "test-cricket-index"
    mock_pc_instance.list_indexes.return_value = [mock_existing_index]
    mock_pc_instance.Index.return_value = mock_index_instance
    mock_pinecone_class.return_value = mock_pc_instance

    # 5. Run indexing
    upserted_count = index_documents(data_path="dummy_path.txt", settings=test_settings)

    # 6. Assertions
    assert upserted_count == 2
    mock_embed_instance.embed_query.assert_called()
    assert mock_embed_instance.embed_query.call_count == 2

    # Verify upsert was called on the mock index with correct payload schema
    mock_index_instance.upsert.assert_called_once()
    called_vectors = mock_index_instance.upsert.call_args.kwargs["vectors"]
    assert len(called_vectors) == 2
    assert called_vectors[0]["id"] == "law_chunk_0"
    assert called_vectors[0]["metadata"]["law_number"] == "38"
    assert called_vectors[0]["metadata"]["text"] == "Law 38.1 Out Run out"