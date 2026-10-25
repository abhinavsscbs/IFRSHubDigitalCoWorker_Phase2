import test from 'node:test';
import assert from 'node:assert/strict';
import { prepareAnswerMarkdown } from '../src/answer-markdown.js';


test('preserves complete Markdown, indentation, code, links and paragraph breaks', () => {
  const answer = '## Conclusion\n\n- **IFRS 16** applies.\n  - Nested point\n\n```text\nx - y\n```\n\n[Guidance](https://example.com)';
  assert.equal(prepareAnswerMarkdown(answer), answer);
});

test('restores explicit bold headings in legacy flattened answers', () => {
  const answer = '## **Conclusion:** - Recognize the asset. ## **Introduction:** - Review the contract. ### **1.1 Assessment principle** The principle applies.';
  const formatted = prepareAnswerMarkdown(answer);
  assert.match(formatted, /^## \*\*Conclusion:\*\*\n\n- Recognize/);
  assert.match(formatted, /\n\n## \*\*Introduction:\*\*\n\n- Review/);
  assert.match(formatted, /\n\n### \*\*1.1 Assessment principle\*\*\n\nThe principle/);
  assert.equal(prepareAnswerMarkdown(formatted), formatted);
});

test('does not guess paragraph boundaries in ordinary plain text', () => {
  const answer = 'Office A - Building B. Amount = x - y. Ordinary text.';
  assert.equal(prepareAnswerMarkdown(answer), answer);
  assert.equal(prepareAnswerMarkdown(null), '');
});
