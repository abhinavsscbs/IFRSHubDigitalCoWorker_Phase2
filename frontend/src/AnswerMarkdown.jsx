import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { prepareAnswerMarkdown } from './answer-markdown';

const components = {
  table: ({ node, ...props }) => <div className="answer-table-scroll" tabIndex={0} role="region" aria-label="Answer table"><table {...props}/></div>,
};

export default function AnswerMarkdown({ text, isArabic = false }) {
  return <article className="markdown" dir={isArabic ? 'rtl' : 'auto'}>
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {prepareAnswerMarkdown(text)}
    </ReactMarkdown>
  </article>;
}
