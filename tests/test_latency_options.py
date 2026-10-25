from unittest.mock import Mock
from langchain_core.documents import Document
from rag_engine import engine


def test_retrieval_mode_skips_llm_gate_but_preserves_empty_context_rejection(monkeypatch):
    judge = Mock()
    monkeypatch.setattr(engine, 'RELEVANCE_MODE', 'retrieval')
    monkeypatch.setattr(engine, 'LLM_RELEVANCE', judge)
    monkeypatch.setattr(engine, 'retrieve_docs_with_score', lambda *args, **kwargs: [(Document(page_content='Source'), .8)])
    assert engine.get_query_relevance_llm('index', 'Question')['label'] == 'relevant'
    judge.invoke.assert_not_called()
    monkeypatch.setattr(engine, 'retrieve_docs_with_score', lambda *args, **kwargs: [])
    assert engine.get_query_relevance_llm('index', 'Question')['label'] == 'irrelevant'
    judge.invoke.assert_not_called()


def test_llm_mode_keeps_semantic_rejection(monkeypatch):
    from langchain_core.messages import AIMessage
    judge = Mock()
    judge.invoke.return_value = AIMessage(content='{"label":"irrelevant","reason":"No supporting context"}')
    monkeypatch.setattr(engine, 'RELEVANCE_MODE', 'llm')
    monkeypatch.setattr(engine, 'LLM_RELEVANCE', judge)
    monkeypatch.setattr(engine, 'retrieve_docs_with_score', lambda *args, **kwargs: [(Document(page_content='Source'), .8)])
    result = engine.get_query_relevance_llm('index', 'Question')
    assert result['label'] == 'irrelevant'
    assert result['reason'] == 'No supporting context'
    judge.invoke.assert_called_once()
