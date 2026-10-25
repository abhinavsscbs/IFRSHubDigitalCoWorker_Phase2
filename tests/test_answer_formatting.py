from backend import app as api
from rag_engine.formatting import format_visible_answer


ANSWER = '''## **Conclusion:**

Recognize a **right-of-use asset** under **IFRS 16**.
Keep this explicit line break.

### Assessment

- First point
  - Nested point with [supporting guidance](https://example.com/ifrs).
- Second point

1. Identify the lease.
2. Measure the liability.

> Consider the contract terms.

| Item | Amount |
| --- | --- |
| Liability | SAR 1,000 |

```python
amount = 1000
if amount:
    print(amount)
```
'''


def test_markdown_structure_reaches_api_without_flattening_or_double_bolding(monkeypatch):
    monkeypatch.setattr(api, 'answer_with_refine_chain', lambda question: {
        'answer_text': ANSWER, 'exception_section': '## Exceptions\n\n- Check the exemption.',
        'sources': [], 'tables': [], 'stage_answers': {'main': ANSWER},
    })
    monkeypatch.setattr(api, 'filter_page_zero_references', lambda sources: sources)
    result = api._run_answer_pipeline('Question')
    assert result['answer'].startswith(ANSWER.rstrip())
    assert '\n\n## Exceptions\n\n- Check the exemption.' in result['answer']
    assert '  - Nested point' in result['answer']
    assert '```python\n' in result['answer']
    assert '****IFRS 16****' not in result['answer']
    assert '[supporting guidance](https://example.com/ifrs)' in result['answer']


def test_visible_formatting_is_idempotent_and_preserves_unicode_and_code():
    answer = '## Résumé\r\n\r\n– تقييم الأصل\r\n  • Nested point\r\n\r\n```text\r\n– literal code\r\n```'
    expected = '## Résumé\n\n- تقييم الأصل\n  - Nested point\n\n```text\n– literal code\n```'
    assert format_visible_answer(answer) == expected
    assert format_visible_answer(format_visible_answer(answer)) == expected


def test_repeated_words_and_markdown_syntax_are_not_rewritten():
    text = '## Conclusion\n\nVery very important.\n\n- **IFRS 16**\n\n    indented code'
    assert format_visible_answer(text) == text
