// Older responses were saved after the backend removed every newline.
// Recover only explicit, bold Markdown headings; avoid guessing paragraph
// boundaries or turning ordinary hyphens in financial text into list items.
export function prepareAnswerMarkdown(value) {
  const text = (typeof value === 'string' ? value : '').replace(/\r\n?/g, '\n');
  if (text.includes('\n') || !/^#{1,6}\s+\*\*/.test(text)) return text;
  return text.replace(/(^|[ \t]+)(#{1,6})[ \t]+(\*\*[^*\n]+\*\*)[ \t]*/g,
    (_, space, level, title) => `${space ? '\n\n' : ''}${level} ${title}\n\n`);
}
