import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import FAISS
from rag_engine import retrieval


class TestEmbeddings(Embeddings):
    __test__ = False
    def embed_documents(self, texts):
        return [[0., 0.] if text == 'near' else [2., 0.] for text in texts]
    def embed_query(self, text):
        return [0., 0.]


@pytest.fixture
def index(tmp_path, monkeypatch):
    embeddings = TestEmbeddings()
    FAISS.from_documents([Document(page_content='near'), Document(page_content='far')], embeddings).save_local(str(tmp_path))
    (tmp_path / 'embedding_manifest.json').write_text(json.dumps({'provider': 'openai', 'model': 'test', 'dimensions': 2}))
    monkeypatch.setattr(retrieval, 'get_embeddings', lambda: embeddings)
    monkeypatch.setattr(retrieval, 'EMBEDDINGS_MODEL', 'test')
    monkeypatch.setattr(retrieval, 'EMBEDDINGS_DIMENSIONS', 2)
    monkeypatch.setattr(retrieval, 'TRUST_LOCAL_INDEXES', True)
    retrieval._load_index_cached.cache_clear()
    retrieval._query_embedding.cache_clear()
    yield tmp_path
    retrieval._load_index_cached.cache_clear()
    retrieval._query_embedding.cache_clear()


def test_real_faiss_ranking_and_squared_l2_score(index):
    docs = retrieval.retrieve_docs_with_score(str(index), 'question', score_threshold=0, max_k=2)
    assert [doc.page_content for doc, _ in docs] == ['near', 'far']
    assert [score for _, score in docs] == pytest.approx([1., .2])
    assert len(retrieval.retrieve_docs_with_score(str(index), 'question', score_threshold=.5)) == 1
    assert len(retrieval.retrieve_docs_with_score(str(index), 'question', top_percentile=.3)) == 1


def test_query_embedding_shared_across_parallel_indexes(monkeypatch):
    embed = Mock(return_value=[0., 0.])
    monkeypatch.setattr(retrieval, 'get_embeddings', lambda: type('Fake', (), {'embed_query': embed})())
    retrieval._query_embedding.cache_clear()
    with ThreadPoolExecutor(5) as pool:
        assert list(pool.map(retrieval.get_query_embedding, ['same question'] * 5)) == [[0., 0.]] * 5
    assert embed.call_count == 1
    retrieval._query_embedding.cache_clear()


def test_index_cached_and_manifest_change_invalidates(index):
    first = retrieval.load_index(str(index))
    assert retrieval.load_index(str(index)) is first
    (index / 'embedding_manifest.json').write_text(json.dumps({'provider': 'openai', 'model': 'wrong', 'dimensions': 2}))
    with pytest.raises(RuntimeError, match='mismatch'):
        retrieval.load_index(str(index))


def test_trust_and_missing_manifest_checks(index, monkeypatch):
    monkeypatch.setattr(retrieval, 'TRUST_LOCAL_INDEXES', False)
    with pytest.raises(RuntimeError, match='trust_local_indexes'):
        retrieval.load_index(str(index))
    monkeypatch.setattr(retrieval, 'TRUST_LOCAL_INDEXES', True)
    (index / 'embedding_manifest.json').unlink()
    with pytest.raises(RuntimeError, match='manifest'):
        retrieval.load_index(str(index))


def test_fetch_preserves_metadata_and_supplies_ids(index):
    docs = retrieval.fetch_docs('question', retrieval.DBConfig(path=str(index), name='IFRS A', top_percentile=1.))
    assert all(doc.metadata['source_db'] == 'IFRS A' and doc.metadata['_doc_id'] for doc in docs)
    assert docs[0].metadata['_similarity_score'] == 1.
