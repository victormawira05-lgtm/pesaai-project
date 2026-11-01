import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { AgGridReact } from 'ag-grid-react';
import { ModuleRegistry, AllCommunityModule, themeQuartz } from 'ag-grid-community';

ModuleRegistry.registerModules([AllCommunityModule]);

const API = import.meta.env.VITE_API_URL ?? 'https://mobile-bankig-api-1.onrender.com';

const gridTheme = themeQuartz.withParams({
  accentColor: '#1b7a3f',
  borderRadius: 8,
  headerBackgroundColor: '#f1f7f2',
  headerTextColor: '#14532d',
  fontFamily: 'Inter, system-ui, Arial, sans-serif',
  oddRowBackgroundColor: '#fafdfb',
});

const usd = (n) => ${n < 0 ? '-' : ''}$${Math.abs(Number(n) || 0).toFixed(2)};
const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random()));

export default function App() {
  const [txns, setTxns] = useState([]);
  const [summary, setSummary] = useState({ income: 0, spent: 0, net: 0 });
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState(null);
  const [lang, setLang] = useState('en');
  const [toasts, setToasts] = useState([]);

  const [amount, setAmount] = useState('10.00');
  const [order, setOrder] = useState(null);
  const [payBusy, setPayBusy] = useState(false);
  const [payMsg, setPayMsg] = useState('');

  const [messages, setMessages] = useState([
    { role: 'assistant', content: "Hi, I'm PesaAI. Ask me about your money, or tell me to send a payment, e.g. \"send $15 to jane@example.com for the logo\"." },
  ]);
  const [input, setInput] = useState('');
  const [coachBusy, setCoachBusy] = useState(false);
  const [proposal, setProposal] = useState(null);
  const [listening, setListening] = useState(false);
  const chatEndRef = useRef(null);
  const nudgedRef = useRef(false);
  const recognitionRef = useRef(null);

  const SpeechRec = typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null;

  const toast = useCallback((text, kind = 'ok') => {
    const id = uuid();
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);

  const post = useCallback(async (path, body, headers = {}) => {
    const res = await fetch(${API}${path}, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(data.detail || data.error || HTTP ${res.status}), { data });
    return data;
  }, []);

  const loadData = useCallback(async () => {
    const res = await fetch(${API}/api/transactions);
    const data = await res.json();
    setTxns(data.transactions || []);
    setSummary(data.summary || { income: 0, spent: 0, net: 0 });
  }, []);

  useEffect(() => {
    fetch(${API}/health).then((r) => r.json()).then(setHealth).catch(() => setHealth(null));
    (async () => {
      try {
        await loadData();
      } catch {
        toast('Could not reach the backend. It may be waking up, retry in a moment.', 'err');
      } finally {
        setLoading(false);
      }
    })();
  }, [loadData, toast]);

  // Proactive coach nudge, once, after data loads.
  useEffect(() => {
    if (loading || nudgedRef.current) return;
    nudgedRef.current = true;
    post('/api/ai/nudge', { lang })
      .then((n) => {
        if (!n?.reply) return;
        setMessages((m) => [...m, { role: 'assistant', content: 💡 ${n.reply} }]);
        if (n.type === 'proposal' && n.action) setProposal({ ...n.action, source: 'nudge' });
      })
      .catch(() => {});
  }, [loading, lang, post]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, proposal]);

  const columnDefs = useMemo(
    () => [
      { field: 'date', headerName: 'Date', width: 120, filter: true },
      { field: 'desc', headerName: 'Description', flex: 1, minWidth: 170, filter: true },
      {
        field: 'amount',
        headerName: 'Amount',
        width: 120,
        filter: 'agNumberColumnFilter',
        valueFormatter: (p) => (p.value == null ? '' : usd(p.value)),
        cellStyle: (p) => ({ color: p.value >= 0 ? '#0a7a00' : '#c0352b', fontWeight: 600, textAlign: 'right' }),
      },
      { field: 'type', headerName: 'Type', width: 120, filter: true, cellRenderer: (p) => <span className="pill">{p.value}</span> },
      {
        field: 'method',
        headerName: 'Method',
        width: 140,
        filter: true,
        cellRenderer: (p) => (
          <span>
            {p.value}
            {p.data?.sim && <span className="sim-tag" title="Illustrative sample data">sim</span>}
          </span>
        ),
      },
    ],
    []
  );

  const pinnedBottom = useMemo(() => [{ desc: 'Net this period', amount: summary.net, type: '', method: '', date: '' }], [summary.net]);

  async function startTopUp() {
    setPayBusy(true);
    setPayMsg('Creating a secure PayPal order...');
    setOrder(null);
    try {
      const data = await post('/api/paypal/create-order', { amount, description: 'PesaAI top-up' });
      setOrder(data);
      if (data.approve_url) {
        window.open(data.approve_url, '_blank', 'noopener');
        setPayMsg('Approve in the PayPal window, then click "Complete top-up".');
      } else {
        setPayMsg(Running in mock mode (order ${data.id}). Click "Complete top-up" to simulate.);
      }
    } catch (e) {
      setPayMsg(Could not create the order: ${e.message});
      toast('Order creation failed', 'err');
    } finally {
      setPayBusy(false);
    }
  }

  async function completeTopUp() {
    if (!order) return;
    setPayBusy(true);
    setPayMsg('Capturing the payment...');
    try {
      const amt = parseFloat(amount) || 0;
      const data = await post(/api/paypal/capture/${order.id}, { amount: amt, description: 'PayPal top-up' });
      if (data.status === 'COMPLETED') {
        await loadData();
        setPayMsg(Top-up complete (${data.mode}). Added ${usd(amt)}.);
        toast(Added ${usd(amt)} via PayPal, 'ok');
      } else {
        setPayMsg(Capture returned status ${data.status}.);
      }
      setOrder(null);
    } catch (e) {
      setPayMsg(Capture failed: ${e.message}. Approve the order in PayPal first.);
      toast('Capture failed', 'err');
    } finally {
      setPayBusy(false);
    }
  }

  async function sendMessage(e) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || coachBusy) return;
    setInput('');
    setProposal(null);
    setMessages((m) => [...m, { role: 'user', content: text }]);
    setCoachBusy(true);
    try {
      const data = await post('/api/ai/agent', { message: text, lang });
      setMessages((m) => [...m, { role: 'assistant', content: data.reply }]);
      if (data.type === 'proposal') setProposal(data.action);
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: Sorry, I hit an error: ${e.message} }]);
    } finally {
      setCoachBusy(false);
    }
  }

  function toggleVoice() {
    if (!SpeechRec) return;
    if (listening) {
      recognitionRef.current?.stop();
      return;
    }
    const rec = new SpeechRec();
    rec.lang = lang === 'sw' ? 'sw-KE' : 'en-US';
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => {
      const transcript = e.results[0][0].transcript;
      setInput((prev) => (prev ? ${prev} ${transcript} : transcript));
    };
    rec.onerror = () => { setListening(false); toast('Voice input unavailable', 'err'); };
    rec.onend = () => setListening(false);
    recognitionRef.current = rec;
    setListening(true);
    try {
      rec.start();
    } catch {
      setListening(false);
    }
  }

  async function getInsights() {
    if (coachBusy) return;
    setMessages((m) => [...m, { role: 'user', content: lang === 'sw' ? 'Nipe uchambuzi wa matumizi yangu' : 'Give me insights on my spending' }]);
    setCoachBusy(true);
    try {
      const data = await post('/api/ai/insights', { lang });
      setMessages((m) => [...m, { role: 'assistant', content: data.insights }]);
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: Sorry, I hit an error: ${e.message} }]);
    } finally {
      setCoachBusy(false);
    }
  }

  async function confirmProposal() {
    if (!proposal) return;
    const p = proposal;
    setProposal(null);
    setCoachBusy(true);
    setMessages((m) => [...m, { role: 'assistant', content: Sending ${usd(p.amount)} to ${p.recipient}... }]);
    try {
      const data = await post('/api/paypal/execute', { amount: p.amount, recipient: p.recipient, reason: p.reason }, { 'Idempotency-Key': uuid() });
      await loadData();
      setMessages((m) => [...m, { role: 'assistant', content: Done. Payout ${data.batch_id} is ${data.status} (${data.mode}). }]);
      toast(Sent ${usd(p.amount)} to ${p.recipient}, 'ok');
    } catch (e) {
      const detail = e.data?.detail || e.message;
      setMessages((m) => [...m, { role: 'assistant', content: I could not complete that payment: ${detail} }]);
      toast('Payment failed', 'err');
    } finally {
      setCoachBusy(false);
    }
  }

  return (
    <div className="app">
      <div className="toasts" aria-live="polite" aria-atomic="false">
        {toasts.map((t) => (
          <div key={t.id} className={toast ${t.kind}}>{t.text}</div>
        ))}
      </div>

      <header className="topbar">
        <div className="brand">
          <Logo />
          <div>
            <h1>PesaAI <span className="badge-ke">KE</span></h1>
            <p className="tagline">AI money coach for Kenyan freelancers paid in USD via PayPal</p>
          </div>
        </div>
        <div className="status" aria-live="polite">
          <StatusChip label="PayPal" value={health ? (health.paypal === 'live' ? 'Sandbox live' : 'mock') : '...'} ok={health?.paypal === 'live'} />
          <StatusChip label="AI" value={health ? (health.ai === 'live' ? health.model : 'mock') : '...'} ok={health?.ai === 'live'} />
        </div>
      </header>

      <section className="stats">
        <StatCard label="Income" value={usd(summary.income)} sub="via PayPal" tone="pos" />
        <StatCard label="Spent" value={usd(-summary.spent)} sub="mostly M-Pesa (sim)" tone="neg" />
        <StatCard label="Net" value={usd(summary.net)} sub="this period" tone="brand" />
      </section>

      <div className="grid-2">
        <section className="card">
          <h2>Transactions</h2>
          <p className="muted small">PayPal rows are real sandbox activity. M-Pesa rows marked <span className="sim-tag">sim</span> are illustrative sample data.</p>
          <div style={{ height: 360, width: '100%' }}>
            <AgGridReact
              theme={gridTheme}
              rowData={txns}
              columnDefs={columnDefs}
              defaultColDef={{ sortable: true, resizable: true }}
              pinnedBottomRowData={pinnedBottom}
              pagination={true}
              paginationPageSize={10}
              paginationPageSizeSelector={false}
              loading={loading}
              overlayNoRowsTemplate="No transactions yet"
            />
          </div>

          <div className="topup">
            <label htmlFor="amt" className="small muted">Add funds with PayPal (USD)</label>
            <div className="row">
              <input id="amt" type="number" min="1" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} disabled={payBusy} />
              {!order ? (
                <button className="btn btn-paypal" onClick={startTopUp} disabled={payBusy || !(parseFloat(amount) > 0)}>
                  {payBusy ? 'Working...' : 'Pay with PayPal'}
                </button>
              ) : (
                <button className="btn btn-paypal" onClick={completeTopUp} disabled={payBusy}>
                  {payBusy ? 'Working...' : 'Complete top-up'}
                </button>
              )}
            </div>
            {payMsg && <div className="notice" aria-live="polite">{payMsg}</div>}
          </div>
        </section>

        <section className="card coach">
          <div className="coach-head">
            <h2>AI Coach</h2>
            <div className="lang" role="group" aria-label="Language">
              <button className={lang === 'en' ? 'on' : ''} onClick={() => setLang('en')} aria-pressed={lang === 'en'}>EN</button>
              <button className={lang === 'sw' ? 'on' : ''} onClick={() => setLang('sw')} aria-pressed={lang === 'sw'}>SW</button>
            </div>
          </div>

          <div className="chat" role="log" aria-live="polite">
            {messages.map((m, i) => (
              <div key={i} className={msg ${m.role}}>{m.content}</div>
            ))}
            {coachBusy && <div className="msg assistant typing">...</div>}

            {proposal && (
              <div className="proposal">
                <div className="proposal-title">Confirm payment{proposal.source === 'nudge' ? ' (suggested)' : ''}</div>
                <dl>
                  <div><dt>Amount</dt><dd>{usd(proposal.amount)}</dd></div>
                  <div><dt>To</dt><dd>{proposal.recipient}</dd></div>
                  {proposal.reason && <div><dt>For</dt><dd>{proposal.reason}</dd></div>}
                </dl>
                <div className="row">
                  <button className="btn btn-brand" onClick={confirmProposal} disabled={coachBusy}>Confirm &amp; send</button>
                  <button className="btn btn-ghost" onClick={() => { setProposal(null); setMessages((m) => [...m, { role: 'assistant', content: 'Cancelled, nothing was sent.' }]); }}>Cancel</button>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <form className="chat-input" onSubmit={sendMessage}>
            <button type="button" className="btn btn-ghost" onClick={getInsights} disabled={coachBusy} title="Analyse my transactions">Insights</button>
            <input
              aria-label="Message the coach"
              placeholder={lang === 'sw' ? 'Andika ujumbe...' : 'Ask, or say "send $15 to..."'}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={coachBusy}
            />
            {SpeechRec && (
              <button
                type="button"
                className={btn btn-ghost mic ${listening ? 'listening' : ''}}
                onClick={toggleVoice}
                disabled={coachBusy}
                aria-pressed={listening}
                aria-label={listening ? 'Stop listening' : 'Speak to the coach'}
                title={listening ? 'Listening, click to stop' : Speak (${lang === 'sw' ? 'Swahili' : 'English'})}
              >
                {listening ? '■' : '🎤'}
              </button>
            )}
            <button type="submit" className="btn btn-brand" disabled={coachBusy || !input.trim()}>Send</button>
          </form>
        </section>
      </div>

      <footer className="foot muted small">
        PesaAI, built for the PayPal AI Hackathon. PayPal runs on the live sandbox, no real money moves. M-Pesa figures are illustrative.
      </footer>
    </div>
  );
}

function Logo() {
  return (
    <svg className="logo" width="40" height="40" viewBox="0 0 40 40" role="img" aria-label="PesaAI logo">
      <circle cx="20" cy="20" r="19" fill="#1b7a3f" />
      <circle cx="20" cy="20" r="13" fill="none" stroke="#bfe4cc" strokeWidth="2" />
      <text x="20" y="26" textAnchor="middle" fontSize="16" fontWeight="700" fill="#fff" fontFamily="Inter, Arial">P</text>
    </svg>
  );
}

function StatCard({ label, value, sub, tone }) {
  return (
    <div className={stat ${tone}}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <div className="stat-sub">{sub}</div>
    </div>
  );
}

function StatusChip({ label, value, ok }) {
  return (
    <span className={chip ${ok ? 'chip-ok' : 'chip-muted'}} title={${label}: ${value}}>
      <span className="dot" /> {label}: {value}
    </span>
  );
}
