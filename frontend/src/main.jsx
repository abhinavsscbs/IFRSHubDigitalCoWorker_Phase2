import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import AnswerMarkdown from './AnswerMarkdown';
import { ArrowUp, ArrowUpRight, BookOpen, Check, ChevronRight, CircleHelp, Clock3, Download, FileText, Globe2, LoaderCircle, MessageSquare, Plus, Search, Sparkles, Trash2, X } from 'lucide-react';
import { request, waitForPrompt, download } from './api';
import './styles.css';

const suggestions = [
  ['Revenue recognition', 'How does IFRS 15 recognize revenue from contracts with customers?', 'IFRS 15'],
  ['Lease accounting', 'How should a lessee initially measure a right-of-use asset under IFRS 16?', 'IFRS 16'],
  ['Financial instruments', 'Explain the expected credit loss approach in IFRS 9.', 'IFRS 9'],
  ['Intangible assets', 'When can development expenditure be recognized as an intangible asset under IAS 38?', 'IAS 38'],
];

function App() {
  const [userId] = useState(() => {
    let value = localStorage.getItem('ifrs-user-id');
    if (!value) { value = crypto.randomUUID(); localStorage.setItem('ifrs-user-id', value); }
    return value;
  });
  const [history, setHistory] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [question, setQuestion] = useState('');
  const [filter, setFilter] = useState('');
  const [health, setHealth] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [showHelp, setShowHelp] = useState(false);
  const [booting, setBooting] = useState(true);
  const controller = useRef(null);
  const textarea = useRef(null);
  const active = history.find(item => item.promptId === activeId);
  const pending = history.some(item => item.promptStatus === 'Thinking');
  const readyCount = health?.indexes?.filter(item => item.available).length || 0;
  const completed = active?.promptStatus === 'Completed';

  const upsert = prompt => setHistory(items => [prompt, ...items.filter(item => item.promptId !== prompt.promptId)]);

  async function refreshHealth() {
    try { setHealth(await request('health')); } catch { setHealth({ status: 'offline' }); }
  }

  useEffect(() => {
    const abort = new AbortController();
    controller.current = abort;
    refreshHealth();
    request(`history?userId=${encodeURIComponent(userId)}`, { signal: abort.signal })
      .then(async data => {
        setHistory(data.history || []);
        // Resume polling jobs left running by a browser refresh.
        await Promise.all((data.history || []).filter(item => item.promptStatus === 'Thinking').map(item =>
          waitForPrompt(item, userId, abort.signal, upsert).catch(err => {
            if (err.name !== 'AbortError') setError(`Could not refresh task status: ${err.message}. Reload to retry.`);
          })));
      })
      .catch(err => { if (err.name !== 'AbortError') setError(err.message); })
      .finally(() => setBooting(false));
    return () => abort.abort();
  }, [userId]);

  async function submit(event, text = question) {
    event?.preventDefault();
    if (!text.trim() || busy || pending) return;
    setBusy(true); setError('');
    const abort = new AbortController(); controller.current = abort;
    try {
      const endpoint = completed ? 'followup' : 'ask';
      const prompt = await request(endpoint, { method: 'POST', signal: abort.signal, data: {
        userId, question: text.trim(), ...(completed ? { promptId: activeId } : {}),
      } });
      upsert(prompt); setActiveId(prompt.promptId); setQuestion('');
      await waitForPrompt(prompt, userId, abort.signal, upsert);
    } catch (err) { if (err.name !== 'AbortError') setError(`${err.message}. Existing tasks continue on the server; reload to reconnect.`); }
    finally { setBusy(false); refreshHealth(); }
  }

  async function translate() {
    setBusy(true); setError('');
    try {
      const prompt = await request('translate', { method: 'POST', data: { userId, promptId: activeId } });
      upsert(prompt);
      await waitForPrompt(prompt, userId, controller.current?.signal, upsert);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function exportHistory(type) {
    setError('');
    try {
      download(await request(`export/${type}`, { method: 'POST', data: { userId }, raw: true }), `ifrs-research.${type}`);
    } catch (err) { setError(err.message); }
  }

  async function clearHistory() {
    setError('');
    try {
      await request('clear', { method: 'POST', data: { userId } });
      setHistory([]); setActiveId(null);
    } catch (err) { setError(err.message); }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="IFRS Hub home"><span className="brand-icon"><BookOpen size={22}/></span><span>IFRS<span className="brand-light">Hub</span><small>DIGITAL CO-WORKER</small></span></a>
      <button className="new-chat" onClick={() => { setActiveId(null); setQuestion(''); textarea.current?.focus(); }}><Plus size={17}/> New research <span>↗</span></button>
      <div className="sidebar-label">WORKSPACE</div>
      <button className={`nav-item ${!active ? 'selected' : ''}`} onClick={() => setActiveId(null)}><Sparkles size={17}/> Research assistant</button>
      <button className="nav-item" onClick={() => setShowHelp(true)}><BookOpen size={17}/> Knowledge sources <span className="count">5</span></button>
      <div className="history-heading"><span className="sidebar-label">RECENT RESEARCH</span><button aria-label="Clear research history" title="Clear history" disabled={busy || pending || !history.length} onClick={clearHistory}><Trash2 size={14}/></button></div>
      <label className="search"><Search size={14}/><input aria-label="Search research history" value={filter} onChange={event => setFilter(event.target.value)} placeholder="Search research"/></label>
      <div className="history-list">{history.filter(item => (item.promptTitle || '').toLowerCase().includes(filter.toLowerCase())).map(item => <button className={`history-item ${activeId === item.promptId ? 'selected' : ''}`} key={item.promptId} onClick={() => setActiveId(item.promptId)}><MessageSquare size={15}/><span>{item.promptTitle}</span>{item.promptStatus === 'Thinking' && <LoaderCircle className="spin" size={14}/>}</button>)}{!history.length && <p className="empty-history">Your research will appear here.</p>}</div>
      <div className="sidebar-bottom"><div className="private-note"><span className="status-dot"/> Local workspace</div><button className="profile" onClick={() => setShowHelp(true)}><span className="avatar">R</span><span>Research workspace<small>IFRS knowledge assistant</small></span><CircleHelp size={16}/></button></div>
    </aside>
    <main>
      <header className="topbar"><div>Workspace <ChevronRight size={14}/><strong>Research assistant</strong></div><span className={`connection ${health?.status === 'ok' ? 'online' : ''}`}><span className="status-dot"/>{health?.status === 'ok' ? 'API connected' : health ? 'API offline' : 'Connecting…'}</span></header>
      <div className="page-area">
        <div className="page-toolbar"><span className="eyebrow">YOUR ACCOUNTING RESEARCH, CONNECTED</span><button className="text-button" onClick={() => setShowHelp(true)}><CircleHelp size={15}/> How it works</button></div>
        {error && <div className="error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError('')}><X size={16}/></button></div>}
        {health?.status === 'ok' && (!health.apiKeyConfigured || readyCount < 5) && <div className="setup-note"><CircleHelp size={16}/><span>{!health.apiKeyConfigured ? 'Add your OpenAI API key to the server .env to begin. ' : ''}{readyCount < 5 ? `${readyCount}/5 knowledge indexes provisioned. See README for setup.` : ''}</span></div>}
        {!active ? <section className="welcome">
          <div className="assistant-badge"><Sparkles size={23}/></div>
          <div className="welcome-kicker">A little clarity. A lot of confidence.</div>
          <h1>Your next accounting question,<br/><span>one conversation away.</span></h1>
          <p className="intro">Explore IFRS standards and expert guidance in one place.<br/>Get clear answers, with the sources to back them up.</p>
          <div className="source-pills"><span><BookOpen size={13}/> IFRS A, B & C</span><span><FileText size={13}/> EY guidance</span><span><FileText size={13}/> PwC guidance</span></div>
          <div className="suggestion-heading">A GOOD PLACE TO START <span>Choose a question or ask your own</span></div>
          <div className="suggestions">{suggestions.map(([title, text, tag]) => <button key={tag} disabled={busy || pending} onClick={() => { setQuestion(text); textarea.current?.focus(); }}><span className="suggestion-top"><span className="standard-tag">{tag}</span><ArrowUpRight size={16}/></span><strong>{title}</strong><span>{text}</span></button>)}</div>
        </section> : <section className="research">
          <div className="answer-heading"><span className="standard-tag">RESEARCH</span><span>{active.promptId}</span></div>
          <h1>{active.renderData?.question || active.promptTitle}</h1>
          <div className="answer-meta"><span><Sparkles size={14}/> IFRS research assistant</span>{active.renderData?.timeTakenSec != null && <span><Clock3 size={14}/>{active.renderData.timeTakenSec.toFixed(1)}s</span>}{active.renderData?.confidence && <span title={active.renderData.confidence.reason}>Retrieval confidence: {active.renderData.confidence.label}</span>}</div>
          {active.promptStatus === 'Thinking' ? <div className="thinking" role="status"><LoaderCircle className="spin" size={20}/><div><strong>Researching your question</strong><p>Reviewing standards and supporting guidance. You can leave this page and return later.</p></div></div> : active.promptStatus === 'Failed' ? <div className="error" role="alert">{active.promptResponseText}</div> : <>
            <AnswerMarkdown text={active.promptResponseText} isArabic={active.renderData?.isArabic}/>
            {(active.renderData?.tables || []).map((table, index) => <div className="table-wrap" key={index}><table><thead><tr>{(table.columns || []).map((col, i) => <th key={i}>{col}</th>)}</tr></thead><tbody>{(table.rows || []).map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{String(cell ?? '')}</td>)}</tr>)}</tbody></table>{active.renderData?.tableData?.[index]?.csv && <button className="text-button" onClick={() => download(new Blob([active.renderData.tableData[index].csv], { type: 'text/csv' }), `table-${index + 1}.csv`)}><Download size={14}/> Download table</button>}</div>)}
            <div className="answer-actions"><button className="text-button" disabled={busy || pending || active.renderData?.isArabic} onClick={translate}><Globe2 size={15}/> Translate to Arabic</button><button className="text-button" onClick={() => exportHistory('pdf')}><Download size={15}/> Export PDF</button><button className="text-button" onClick={() => exportHistory('html')}><FileText size={15}/> Export HTML</button></div>
            <div className="sources-title"><BookOpen size={17}/><strong>Supporting sources</strong><span>{active.renderData?.sources?.length || 0}</span></div>
            <div className="sources">{(active.renderData?.sources || []).map((source, index) => <details key={index}><summary><span className="source-number">{index + 1}</span><div><strong>{source.doc_name || source.chapter_name || 'Document'}</strong><small>{source.publisher} · {source.chapter_name} · Paragraph {source.para_number} · Page {source.page}</small></div><ChevronRight size={16}/></summary><p>{source.excerpt}</p></details>)}</div>
          </>}
        </section>}
        <div className="composer-area"><form className="composer" onSubmit={submit}><textarea ref={textarea} aria-label={completed ? 'Ask a follow-up question' : 'Ask an accounting question'} rows={2} value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(event); } }} placeholder={completed ? 'Dig deeper. Ask a follow-up question…' : 'Ask anything about IFRS and accounting standards…'}/><div className="composer-bottom"><span><span className="tiny-spark"><Sparkles size={13}/></span>{completed ? 'Follow-up research' : 'Grounded in your knowledge sources'}</span><button className="send" type="submit" disabled={!question.trim() || busy || pending || booting} aria-label="Send question">{busy || pending ? <LoaderCircle className="spin" size={19}/> : <ArrowUp size={20}/>}</button></div></form><div className="composer-caption"><span><Check size={12}/> Source-backed answers</span><span>AI can make mistakes. Verify critical accounting decisions.</span><span>Enter to send · Shift + Enter for a new line</span></div></div>
      </div>
      <footer>Built for thoughtful research.<span>IFRS Digital Co-worker</span></footer>
    </main>
    {showHelp && <div className="modal-backdrop" onClick={() => setShowHelp(false)}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="help-title" onClick={event => event.stopPropagation()}><button className="close-modal" onClick={() => setShowHelp(false)} autoFocus aria-label="Close details"><X size={19}/></button><div className="assistant-badge"><BookOpen size={22}/></div><h2 id="help-title">Your research workspace</h2><p>Ask a question to search your five knowledge sources. Review the answer and its sources, ask follow-ups, translate to Arabic, or export the conversation.</p><ul>{(health?.indexes || [{name:'IFRS A'}, {name:'IFRS B'}, {name:'IFRS C'}, {name:'EY'}, {name:'PwC'}]).map(index => <li key={index.name}><BookOpen size={15}/>{index.name}<span>{index.available ? 'Provisioned' : 'Awaiting setup'}</span></li>)}</ul><p className="help-note">History is stored on your Flask server using this browser’s workspace ID. This ID is not authentication; add your organization’s sign-in before sharing the app.</p><button className="new-chat" onClick={() => setShowHelp(false)}>Back to research <ArrowUpRight size={16}/></button></section></div>}
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
