import pytest
from backend import app as api
from backend.session_store import SessionStore


class InlineExecutor:
    def submit(self, fn, *args):
        fn(*args)


@pytest.fixture
def client(tmp_path, monkeypatch):
    import backend.session_store as store_module
    monkeypatch.setattr(store_module, 'CHAT_HISTORY_DIR', str(tmp_path))
    monkeypatch.setattr(api, 'session_store', SessionStore())
    monkeypatch.setattr(api, 'PROMPT_WORKERS', InlineExecutor())
    monkeypatch.setattr(api, '_run_answer_pipeline', lambda question: {
        'answer': f'Answer: {question}', 'stage_answers': {}, 'sources': [{'doc_name': 'IFRS test', 'excerpt': 'Test source'}],
        'confidence': {'label': 'high', 'score': .9}, 'time_taken_sec': .1, 'has_tables': False,
        'table_data': [], 'tables': [], 'promptResponseTabularData': {'headers': [], 'rows': []},
    })
    return api.app.test_client()


def ask(client, question='Question'):
    return client.post('/api/ask', json={'userId': 'test', 'question': question}).get_json()['payload']


def status(client, prompt, user='test'):
    return client.post('/api/updatestatus', json={'userId': user, 'promptId': prompt['promptId']})


def test_async_ask_followup_history_and_export(client):
    prompt = ask(client)
    assert prompt['promptStatus'] == 'Thinking'
    done = status(client, prompt).get_json()['payload']
    assert done['isTerminal'] is True and done['promptStatus'] == 'Completed'
    assert done['renderData']['sources'][0]['doc_name'] == 'IFRS test'
    followup = client.post('/api/followup', json={'userId': 'test', 'question': 'More detail', 'promptId': prompt['promptId']}).get_json()['payload']
    assert 'Question More detail' in status(client, followup).get_json()['payload']['promptResponseText']
    assert len(client.get('/api/history?userId=test').get_json()['payload']['history']) == 2
    assert status(client, prompt, 'different-user').status_code == 404
    exported = client.post('/api/export/html', json={'userId': 'test'})
    assert exported.status_code == 200 and 'text/html' in exported.content_type
    client.post('/api/clear', json={'userId': 'test'})
    assert client.get('/api/history?userId=test').get_json()['payload']['history'] == []


def test_pipeline_failure_is_terminal(client, monkeypatch):
    def fail(question):
        raise RuntimeError('Missing trusted index')
    monkeypatch.setattr(api, '_run_answer_pipeline', fail)
    result = status(client, ask(client)).get_json()['payload']
    assert result['promptStatus'] == 'Failed' and result['isTerminal'] is True
    assert 'Missing trusted index' in result['promptResponseText']


def test_translate_targets_selected_prompt(client, monkeypatch):
    first = ask(client, 'First')
    second = ask(client, 'Second')
    monkeypatch.setattr(api, 'translate_to_arabic', lambda text: 'ترجمة ' + text)
    translated = client.post('/api/translate', json={'userId': 'test', 'promptId': first['promptId']})
    assert translated.status_code == 200
    assert translated.get_json()['payload']['promptId'] == first['promptId']
    assert translated.get_json()['payload']['renderData']['isArabic'] is True
    assert status(client, second).get_json()['payload']['renderData']['isArabic'] is False
    assert client.post('/api/translate', json={'userId': 'test', 'promptId': 'missing'}).status_code == 404


def test_health_and_validation(client):
    health = client.get('/api/health').get_json()
    assert health['status'] == 'ok' and len(health['indexes']) == 5
    assert 'api_key' not in str(health).lower()
    assert client.post('/api/ask', json={'userId': 'test', 'question': ''}).status_code == 400
    assert client.post('/api/ask', json={'question': 'hello'}).status_code == 400
