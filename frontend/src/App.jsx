import { useEffect, useState } from 'react';

const API_ROOT = '/api';

function readSession() {
  try {
    return JSON.parse(localStorage.getItem('research-os-session'));
  } catch {
    return null;
  }
}

export default function App() {
  const [session, setSession] = useState(readSession);
  const [authMode, setAuthMode] = useState('login');
  const [authForm, setAuthForm] = useState({ username: '', email: '', password: '' });
  const [authLoading, setAuthLoading] = useState(false);
  const [query, setQuery] = useState('AI');
  const [results, setResults] = useState([]);
  const [history, setHistory] = useState([]);
  const [activeView, setActiveView] = useState('search');
  const [loading, setLoading] = useState(false);
  const [claimForm, setClaimForm] = useState(null);
  const [evidenceForm, setEvidenceForm] = useState(null);
  const [currentClaim, setCurrentClaim] = useState(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [error, setError] = useState('');

  const loadHistory = async (token = session?.token) => {
    if (!token) return;
    const response = await fetch(`${API_ROOT}/search-history`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) setHistory(await response.json());
  };

  useEffect(() => {
    if (session?.token) loadHistory();
  }, [session?.token]);

  const submitAuth = async (event) => {
    event.preventDefault();
    setAuthLoading(true);
    setError('');
    try {
      const endpoint = authMode === 'login' ? 'login' : 'register';
      const body = authMode === 'login'
        ? { username: authForm.username, password: authForm.password }
        : authForm;
      const response = await fetch(`${API_ROOT}/auth/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Authentication failed');
      const nextSession = { token: data.token, user: data.user };
      localStorage.setItem('research-os-session', JSON.stringify(nextSession));
      setSession(nextSession);
      setAuthForm({ username: '', email: '', password: '' });
    } catch (err) {
      setError(err.message || 'Authentication failed');
    } finally {
      setAuthLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem('research-os-session');
    setSession(null);
    setResults([]);
    setHistory([]);
    setClaimForm(null);
    setEvidenceForm(null);
    setCurrentClaim(null);
  };

  const startClaim = (item) => {
    setError('');
    setClaimForm({ claim_text: item.title, source: item });
    setActiveView('claims');
  };

  const createClaim = async (event) => {
    event.preventDefault();
    setEvidenceLoading(true);
    setError('');
    try {
      const response = await fetch(`${API_ROOT}/claims`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${session.token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ claim_text: claimForm.claim_text, status: 'draft' }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Failed to create claim');
      setCurrentClaim(data);
      setClaimForm(null);
      setEvidenceForm({ claimId: data.id, source: claimForm.source, excerpt: '', evidence_type: 'abstract', relation: 'uncertain', confidence: '' });
    } catch (err) {
      setError(err.message || 'Failed to create claim');
    } finally {
      setEvidenceLoading(false);
    }
  };

  const startEvidence = (item) => {
    if (!currentClaim) {
      setError('Create a claim before adding evidence.');
      setActiveView('claims');
      return;
    }
    setError('');
    setEvidenceForm({ claimId: currentClaim.id, source: item, excerpt: '', evidence_type: 'abstract', relation: 'uncertain', confidence: '' });
    setActiveView('claims');
  };

  const createEvidence = async (event) => {
    event.preventDefault();
    if (!evidenceForm.excerpt.trim()) {
      setError('Enter the exact excerpt or abstract text before saving evidence.');
      return;
    }
    setEvidenceLoading(true);
    setError('');
    const source = evidenceForm.source;
    try {
      const evidenceResponse = await fetch(`${API_ROOT}/evidence`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${session.token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_id: source.source_id || null,
          source_title: source.title,
          authors: source.authors || [],
          year: source.year || null,
          doi: source.doi || null,
          url: source.url || null,
          excerpt: evidenceForm.excerpt,
          evidence_type: evidenceForm.evidence_type,
          relation: evidenceForm.relation,
          confidence: evidenceForm.confidence === '' ? null : Number(evidenceForm.confidence),
        }),
      });
      const evidence = await evidenceResponse.json();
      if (!evidenceResponse.ok) throw new Error(evidence.detail || 'Failed to create evidence');

      const linkResponse = await fetch(`${API_ROOT}/claims/${evidenceForm.claimId}/evidence`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${session.token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ evidence_id: evidence.id }),
      });
      const claim = await linkResponse.json();
      if (!linkResponse.ok) throw new Error(claim.detail || 'Failed to link evidence');
      setCurrentClaim(claim);
      setEvidenceForm(null);
    } catch (err) {
      setError(err.message || 'Failed to save evidence');
    } finally {
      setEvidenceLoading(false);
    }
  };

  const fetchResults = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError('');
    try {
      const headers = session?.token ? { Authorization: `Bearer ${session.token}` } : {};
      const response = await fetch(`${API_ROOT}/search?q=${encodeURIComponent(query)}`, { headers });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Failed to fetch results');
      setResults(data.results || []);
      if (session?.token) await loadHistory();
    } catch (err) {
      setError(err.message || 'Unexpected error');
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  if (!session) {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <div className="brand">Research OS</div>
          <p className="eyebrow">Academic Research Workspace</p>
          <h1>{authMode === 'login' ? 'Welcome back' : 'Create your workspace'}</h1>
          <p className="auth-copy">Search trusted academic sources and keep your research organized.</p>
          <form className="auth-form" onSubmit={submitAuth}>
            <input required value={authForm.username} onChange={(e) => setAuthForm({ ...authForm, username: e.target.value })} placeholder="Username" />
            {authMode === 'register' && <input required type="email" value={authForm.email} onChange={(e) => setAuthForm({ ...authForm, email: e.target.value })} placeholder="Email" />}
            <input required minLength={8} type="password" value={authForm.password} onChange={(e) => setAuthForm({ ...authForm, password: e.target.value })} placeholder="Password (8+ characters)" />
            <button className="primary" type="submit" disabled={authLoading}>{authLoading ? 'Please wait...' : authMode === 'login' ? 'Login' : 'Register'}</button>
          </form>
          {error && <div className="alert">{error}</div>}
          <button className="text-button" onClick={() => { setAuthMode(authMode === 'login' ? 'register' : 'login'); setError(''); }}>
            {authMode === 'login' ? 'Need an account? Register' : 'Already have an account? Login'}
          </button>
        </section>
      </main>
    );
  }

  const exportCsv = () => {
    if (!results.length) return;

    const headers = ['title', 'authors', 'year', 'doi', 'url', 'source', 'abstract', 'citation_count'];
    const csv = [headers.join(',')]
      .concat(
        results.map((item) =>
          headers
            .map((key) => `"${String(key === 'authors' ? (item.authors || []).join('; ') : item[key] ?? '').replace(/"/g, '""')}"`)
            .join(',')
        )
      )
      .join('\n');

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `research-results-${query.replace(/\s+/g, '-').toLowerCase()}.csv`;
    link.click();
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">Research OS</div>
        <nav>
          <button className={`nav-item ${activeView === 'search' ? 'active' : ''}`} onClick={() => setActiveView('search')}>Search</button>
          <button className={`nav-item ${activeView === 'history' ? 'active' : ''}`} onClick={() => setActiveView('history')}>My Research History</button>
          <button className={`nav-item ${activeView === 'claims' ? 'active' : ''}`} onClick={() => setActiveView('claims')}>Claims and Evidence</button>
        </nav>
        <div className="user-box">
          <strong>{session.user.username}</strong>
          <small>{session.user.email}</small>
          <button className="text-button" onClick={logout}>Log out</button>
        </div>
      </aside>

      <main className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">Academic Research Workspace</p>
            <h1>{activeView === 'search' ? 'Search and discover' : activeView === 'history' ? 'My Research History' : 'Claims and Evidence'}</h1>
          </div>
          {activeView === 'search' && <button className="primary" onClick={exportCsv} disabled={!results.length}>Export CSV</button>}
        </header>

        {activeView === 'search' ? (
          <>
            <section className="search-panel">
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search for a topic..." />
              <button onClick={fetchResults} disabled={loading}>{loading ? 'Searching...' : 'Search'}</button>
            </section>

            {error && <div className="alert">{error}</div>}

            <section className="results">
              {results.length ? results.map((item, index) => (
                <article key={`${item.source_id || item.doi || item.title}-${index}`} className="result-item">
                  <div className="badge">{item.source}</div>
                  <h3>{item.title}</h3>
                  {item.authors?.length > 0 && <p>{item.authors.join(', ')}</p>}
                  {item.year != null && <p>{item.year}</p>}
                  {item.abstract && <p>{item.abstract}</p>}
                  {item.citation_count != null && <p>{item.citation_count} citations</p>}
                  {item.doi && <p>DOI: {item.doi}</p>}
                  {item.url && <a href={item.url} target="_blank" rel="noreferrer">Open source</a>}
                  <div className="result-actions">
                    <button className="secondary" onClick={() => startClaim(item)}>Create claim</button>
                    <button className="text-button" onClick={() => startEvidence(item)}>Add evidence</button>
                  </div>
                </article>
              )) : <div className="empty-state">No results yet. Try searching for a keyword.</div>}
            </section>
          </>
        ) : activeView === 'history' ? (
          <section className="results">
            {history.length ? history.map((entry) => {
              let count = 0;
              try { count = JSON.parse(entry.results).length; } catch { /* Keep malformed legacy entries readable. */ }
              return (
                <article key={entry.id} className="result-item history-item">
                  <div><strong>{entry.query}</strong><span>{entry.created_at}</span></div>
                  <p>{count} results saved</p>
                  <button className="text-button" onClick={() => { setQuery(entry.query); setActiveView('search'); }}>Search again</button>
                </article>
              );
            }) : <div className="empty-state">No saved searches yet. Run a search to build your history.</div>}
          </section>
        ) : (
          <section className="evidence-workspace">
            {claimForm && (
              <form className="evidence-form" onSubmit={createClaim}>
                <h2>Create a claim</h2>
                <p className="form-context">Based on: {claimForm.source.title}</p>
                <textarea required value={claimForm.claim_text} onChange={(e) => setClaimForm({ ...claimForm, claim_text: e.target.value })} placeholder="Write the research claim..." />
                <button className="primary" type="submit" disabled={evidenceLoading}>{evidenceLoading ? 'Saving...' : 'Create claim'}</button>
              </form>
            )}

            {evidenceForm && (
              <form className="evidence-form" onSubmit={createEvidence}>
                <h2>Add evidence</h2>
                <p className="form-context">Source: {evidenceForm.source.title}</p>
                <label>
                  Evidence type
                  <select value={evidenceForm.evidence_type} onChange={(e) => setEvidenceForm({ ...evidenceForm, evidence_type: e.target.value })}>
                    <option value="abstract">Abstract</option>
                    <option value="full_text">Full text</option>
                  </select>
                </label>
                <label>
                  Relation to claim
                  <select value={evidenceForm.relation} onChange={(e) => setEvidenceForm({ ...evidenceForm, relation: e.target.value })}>
                    <option value="supporting">Supporting</option>
                    <option value="contradicting">Contradicting</option>
                    <option value="uncertain">Uncertain</option>
                  </select>
                </label>
                <label>
                  Exact excerpt or abstract
                  <textarea required value={evidenceForm.excerpt} onChange={(e) => setEvidenceForm({ ...evidenceForm, excerpt: e.target.value })} placeholder="Paste the text that actually supports this evidence..." />
                </label>
                <label>
                  Confidence (optional, 0 to 1)
                  <input type="number" min="0" max="1" step="0.01" value={evidenceForm.confidence} onChange={(e) => setEvidenceForm({ ...evidenceForm, confidence: e.target.value })} />
                </label>
                <button className="primary" type="submit" disabled={evidenceLoading}>{evidenceLoading ? 'Saving...' : 'Save and link evidence'}</button>
              </form>
            )}

            {currentClaim ? (
              <article className="claim-panel">
                <div className="badge">Claim · {currentClaim.status}</div>
                <h2>{currentClaim.claim_text}</h2>
                {currentClaim.evidence?.length ? currentClaim.evidence.map((item) => (
                  <div className="evidence-item" key={item.id}>
                    <div className="evidence-meta">
                      <strong>{item.evidence_type === 'abstract' ? 'Abstract evidence' : 'Full-text evidence'}</strong>
                      <span>{item.relation}</span>
                    </div>
                    <p>{item.excerpt}</p>
                    <small>{item.source_title}{item.year ? ` · ${item.year}` : ''}{item.confidence != null ? ` · confidence ${item.confidence}` : ''}</small>
                  </div>
                )) : <p className="empty-state">No evidence linked yet. Create evidence from a search result.</p>}
              </article>
            ) : <div className="empty-state">Create a claim from a search result to begin tracing evidence.</div>}
          </section>
        )}
      </main>
    </div>
  );
}
