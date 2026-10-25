from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from rag_engine import llm_client as client


def response(**overrides):
    values = dict(status="completed", output_text="A sourced answer", incomplete_details=None, error=None,
                  model="gpt-6.1-sol", id="resp_test", usage=SimpleNamespace(input_tokens=10, output_tokens=20, total_tokens=30))
    return SimpleNamespace(**{**values, **overrides})


def test_full_task_uses_exact_model_and_128k_response_limit(monkeypatch):
    create = Mock(return_value=response())
    monkeypatch.setattr(client, 'get_openai_client', lambda: SimpleNamespace(responses=SimpleNamespace(create=create)))
    answer = client.get_llm('full').invoke([SystemMessage(content='Use sources'), HumanMessage(content='Question'), AIMessage(content='Earlier answer')])
    payload = create.call_args.kwargs
    assert payload['model'] == 'gpt-6.1-sol'
    assert payload['max_output_tokens'] == 128000
    assert payload['store'] is False
    assert 'temperature' not in payload
    assert [item['role'] for item in payload['input']] == ['system', 'user', 'assistant']
    assert answer.content == 'A sourced answer'
    assert answer.usage_metadata['total_tokens'] == 30


@pytest.mark.parametrize('task', ['mini', 'relevance', 'extractor'])
def test_small_tasks_route_to_luna(task):
    assert client.response_options(task)['model'] == 'gpt-6-luna'


def test_unknown_task_rejected():
    with pytest.raises(ValueError, match='Unknown LLM task'):
        client.get_llm('typo')


@pytest.mark.parametrize('item, message', [(response(status='incomplete', incomplete_details='max_output_tokens'), 'incomplete'),
                                         (response(output_text=''), 'no text')])
def test_incomplete_and_refused_responses_are_not_silently_accepted(item, message):
    with pytest.raises(RuntimeError, match=message):
        client.response_text(item)


def test_missing_key_has_actionable_error(monkeypatch):
    monkeypatch.setattr(client, 'OPENAI_API_KEY', '')
    with pytest.raises(RuntimeError, match='OPENAI_API_KEY'):
        client.require_api_key()
