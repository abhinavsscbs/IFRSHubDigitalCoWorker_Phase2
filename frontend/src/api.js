const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export async function request(path, { method = 'GET', data, signal, raw = false } = {}) {
  const response = await fetch(`${base}/api/${path}`, {
    method, signal,
    headers: data ? { 'Content-Type': 'application/json' } : {},
    body: data ? JSON.stringify(data) : undefined,
  });
  if (raw && response.ok) return response.blob();
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.success === false) {
    throw new Error(body.errors?.join('; ') || body.error || `Request failed (${response.status})`);
  }
  return body.payload || body;
}

export async function waitForPrompt(prompt, userId, signal, onUpdate) {
  let current = prompt;
  // The server owns task lifetime. No fixed poll limit truncates long answers.
  while (!current.isTerminal && !['Completed', 'Failed'].includes(current.promptStatus)) {
    current = await request('updatestatus', {
      method: 'POST', signal,
      data: { userId, promptId: current.promptId, waitForTerminalMs: 20000 },
    });
    onUpdate(current);
    if (!current.isTerminal && !['Completed', 'Failed'].includes(current.promptStatus)) {
      await new Promise((resolve, reject) => {
        const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
        const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, Math.max(250, current.retryAfterMs || 1500));
        if (signal?.aborted) abort();
        else signal?.addEventListener('abort', abort, { once: true });
      });
    }
  }
  return current;
}

export function download(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
