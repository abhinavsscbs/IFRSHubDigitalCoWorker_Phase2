import json
import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import FAISS
from rag_engine import config, retrieval
from scripts.rebuild_indexes import rebuild


class FixtureEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[float(i), 0.] for i, _ in enumerate(texts)]
    def embed_query(self, text):
        return [0., 0.]


def test_migration_preserves_source_and_metadata_and_outputs_compatible_index(tmp_path, monkeypatch):
    source, output = tmp_path / 'legacy', tmp_path / 'openai'
    embeddings = FixtureEmbeddings()
    documents = [Document(page_content='Source content', metadata={'chapter_name':'IFRS 15','para_number':'31'})]
    FAISS.from_documents(documents, embeddings).save_local(str(source))
    original = (source / 'index.faiss').read_bytes(), (source / 'index.pkl').read_bytes()
    monkeypatch.setattr(retrieval, 'get_embeddings', lambda: embeddings)
    monkeypatch.setattr(config, 'EMBEDDINGS_MODEL', 'fixture-model')
    monkeypatch.setattr(config, 'EMBEDDINGS_DIMENSIONS', 2)
    with pytest.raises(ValueError, match='trust-source'):
        rebuild(source, output, False)
    rebuild(source, output, True)
    manifest = json.loads((output / 'embedding_manifest.json').read_text())
    assert manifest['model'] == 'fixture-model' and manifest['dimensions'] == 2
    migrated = FAISS.load_local(str(output), embeddings, allow_dangerous_deserialization=True)
    doc = migrated.docstore.search(migrated.index_to_docstore_id[0])
    assert doc.page_content == documents[0].page_content and doc.metadata == documents[0].metadata
    assert original == ((source / 'index.faiss').read_bytes(), (source / 'index.pkl').read_bytes())
    with pytest.raises(ValueError, match='overwrite'):
        rebuild(source, output, True)


def test_unwritable_output_fails_before_creating_embeddings(tmp_path, monkeypatch):
    from unittest.mock import Mock
    import scripts.rebuild_indexes as migration
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'index.faiss').touch()
    (source / 'index.pkl').touch()
    embeddings = Mock()
    monkeypatch.setattr(retrieval, 'get_embeddings', embeddings)
    def denied(*args, **kwargs):
        raise PermissionError('Output directory is not writable')
    monkeypatch.setattr(migration, 'TemporaryFile', denied)
    with pytest.raises(PermissionError, match='not writable'):
        rebuild(source, tmp_path / 'output', True)
    embeddings.assert_not_called()
