import { useCallback, useEffect, useState } from 'react';
import { api, type AgentInfo, type Approval, type AuditEvent, type Execution, type Memory, type SkillInfo } from './services/api';

type Tab = 'command' | 'memory' | 'agents' | 'skills' | 'tools' | 'activity';

export default function App() {
  const [tab, setTab] = useState<Tab>('command');
  return (
    <div className="aether">
      <nav className="side">
        <div className="brand">AETHER<small>Your memory. Your skills. Your agents. Your rules.</small></div>
        {([['command', 'Command Center'], ['memory', 'Memory'], ['agents', 'Agents'], ['skills', 'Skills'], ['tools', 'Tools'], ['activity', 'Activity']] as [Tab, string][]).map(([k, label]) => (
          <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{label}</button>
        ))}
      </nav>
      <main>
        {tab === 'command' && <CommandCenter />}
        {tab === 'memory' && <MemoryPage />}
        {tab === 'agents' && <AgentsPage />}
        {tab === 'skills' && <SkillsPage />}
        {tab === 'tools' && <ToolsPage />}
        {tab === 'activity' && <ActivityPage />}
      </main>
    </div>
  );
}

function usePoll<T>(fn: () => Promise<T>, ms: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const load = useCallback(() => { fn().then(setData).catch(() => {}); }, deps);
  useEffect(() => { load(); const t = setInterval(load, ms); return () => clearInterval(t); }, [load, ms]);
  return { data, reload: load };
}

function CommandCenter() {
  const [msg, setMsg] = useState('Prepare my research meeting for tomorrow.');
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<any>(null);
  const approvals = usePoll(() => api.approvals(), 3000);
  const executions = usePoll(() => api.executions(), 3000);
  const activity = usePoll(() => api.activity(), 4000);

  const send = async () => {
    if (!msg.trim() || busy) return;
    setBusy(true);
    try {
      const r = await api.command(msg);
      setLast(r);
      executions.reload(); approvals.reload(); activity.reload();
    } catch (e: any) { setLast({ error: String(e) }); } finally { setBusy(false); }
  };

  const resolve = async (id: string, approved: boolean) => {
    await api.resolveApproval(id, approved);
    approvals.reload(); executions.reload(); activity.reload();
  };

  return (
    <div>
      <div className="card">
        <h3>Command interface</h3>
        <div className="row">
          <input value={msg} onChange={e => setMsg(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} placeholder="Ask AETHER anything…" />
          <button className="primary" onClick={send} disabled={busy}>{busy ? '…' : 'Run'}</button>
        </div>
        {last && <pre className="result">{JSON.stringify({ state: last.state, agent: last.agent, skill: last.skill, result: last.result, error: last.error }, null, 2)}</pre>}
      </div>
      <div className="grid">
        <div>
          <div className="card">
            <h3>Pending approvals ({approvals.data?.length ?? 0})</h3>
            {!approvals.data?.length && <div className="muted">Nothing waiting.</div>}
            {approvals.data?.map(a => (
              <div key={a.id} className="approval">
                <b>PERMISSION REQUEST</b> — {a.agent} wants to <b>{a.action}</b> via {a.tool}
                <div className="muted">{a.reason} · risk: {a.risk} · {a.resource}</div>
                <div className="row" style={{ marginTop: 8 }}>
                  <button className="primary" onClick={() => resolve(a.id, true)}>Approve Once</button>
                  <button className="danger" onClick={() => resolve(a.id, false)}>Deny</button>
                </div>
              </div>
            ))}
          </div>
          <div className="card">
            <h3>Active tasks</h3>
            {executions.data?.filter(e => !['COMPLETED', 'FAILED'].includes(e.state)).map(e => (
              <div key={e.id} className="muted">{e.agent || '?'} · {e.state} · {e.user_request.slice(0, 80)}</div>
            )) || <div className="muted">—</div>}
            <h3 style={{ marginTop: 12 }}>Recent</h3>
            {executions.data?.slice(0, 5).map(e => (
              <div key={e.id} style={{ fontSize: 13 }}><span className="pill">{e.state}</span><b>{e.agent}</b> — {e.user_request.slice(0, 90)}</div>
            ))}
          </div>
        </div>
        <div className="card">
          <h3>Live activity</h3>
          <div className="timeline">
            {activity.data?.slice(0, 15).map((e, i) => (
              <div key={i} className="ev"><b>{e.action}</b> <span className="muted">{e.agent} · {e.permission} · {e.status}</span><br /><span className="muted">{e.reason?.slice(0, 120)}</span></div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function MemoryPage() {
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('');
  const [mems, setMems] = useState<Memory[]>([]);
  const [ctype, setCtype] = useState('FACT');
  const [ccontent, setCcontent] = useState('');
  const load = useCallback(async () => setMems(await api.memories(filter || undefined)), [filter]);
  useEffect(() => { load(); }, [load]);
  const search = async () => { if (q.trim()) setMems(await api.searchMemory(q)); };
  return (
    <div>
      <div className="card"><h3>Search memory</h3>
        <div className="row"><input value={q} onChange={e => setQ(e.target.value)} placeholder="semantic search…" /><button className="primary" onClick={search}>Search</button>
          <select value={filter} onChange={e => setFilter(e.target.value)} style={{ maxWidth: 160 }}><option value="">all types</option>{['FACT', 'PREFERENCE', 'PROJECT', 'GOAL', 'DECISION', 'EXPERIENCE', 'SKILL', 'WORKFLOW'].map(t => <option key={t} value={t}>{t}</option>)}</select></div>
      </div>
      <div className="card"><h3>Add memory</h3>
        <div className="row"><select value={ctype} onChange={e => setCtype(e.target.value)} style={{ maxWidth: 160 }}>{['FACT', 'PREFERENCE', 'PROJECT', 'GOAL', 'DECISION', 'EXPERIENCE', 'SKILL', 'WORKFLOW'].map(t => <option key={t} value={t}>{t}</option>)}</select>
          <input value={ccontent} onChange={e => setCcontent(e.target.value)} placeholder="content worth remembering…" /><button className="primary" onClick={async () => { await api.createMemory(ctype, ccontent); setCcontent(''); load(); }}>Save</button></div>
      </div>
      {mems.map(m => (
        <div key={m.id} className="mem"><span className="pill">{m.type}</span><span className="pill">conf {m.confidence}</span>{m.score != null && <span className="pill green">score {m.score}</span>}
          <div style={{ margin: '6px 0' }}>{m.content}</div>
          <div className="muted">{m.source} · {new Date(m.updated_at).toLocaleString()} <button className="ghost" style={{ marginLeft: 8 }} onClick={async () => { await api.deleteMemory(m.id); load(); }}>delete</button></div>
        </div>
      ))}
    </div>
  );
}

function AgentsPage() {
  const { data } = usePoll(() => api.agents(), 4000);
  return <div>{data?.map((a: AgentInfo) => (
    <div key={a.name} className="card"><h3>{a.name}</h3><div>{a.description}</div>
      <div style={{ marginTop: 6 }}>{a.capabilities.map(c => <span key={c} className="pill">{c}</span>)}{a.tools.map(t => <span key={t} className="pill green">{t}</span>)}</div>
      <div className="muted" style={{ marginTop: 6 }}>{a.active.length ? `ACTIVE: ${a.active[0].state} — ${a.active[0].user_request.slice(0, 100)}` : 'idle'}</div>
    </div>))}</div>;
}

function SkillsPage() {
  const { data, reload } = usePoll(() => api.skills(), 5000);
  const [out, setOut] = useState<string>('');
  return <div>{data?.map((s: SkillInfo) => (
    <div key={s.name} className="card"><h3>{s.name} v{s.version}</h3><div>{s.description}</div>
      <div style={{ margin: '6px 0' }}>{s.required_tools.map(t => <span key={t} className="pill green">{t}</span>)}{s.required_permissions.map(p => <span key={p} className="pill amber">{p}</span>)}<span className="pill">{s.agent}</span></div>
      <button className="ghost" onClick={async () => { const r = await api.runSkill(s.name, s.name); setOut(JSON.stringify(r, null, 2)); reload(); }}>Run skill</button>
    </div>))}
    {out && <pre className="result">{out}</pre>}</div>;
}

function ToolsPage() {
  const { data } = usePoll(() => api.tools(), 5000);
  const models = usePoll(() => api.models(), 10000);
  return <div>
    <div className="card"><h3>Model router</h3><div className="muted">provider: {models.data?.status?.provider ?? models.data?.provider} · model: {models.data?.status?.model} · status: {models.data?.status?.state}</div></div>
    {data?.map((t: any) => (
      <div key={t.name} className="card"><h3>{t.name} · {t.risk_level}</h3><div>{t.description}</div>
        <div style={{ marginTop: 6 }}>{(t.required_permissions || []).map((p: string) => <span key={p} className="pill amber">{p}</span>)}</div></div>))}
  </div>;
}

function ActivityPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [detail, setDetail] = useState<any>(null);
  useEffect(() => { api.activity().then(setEvents).catch(() => {}); }, []);
  return <div className="card"><h3>Audit journal ({events.length})</h3>
    <div className="timeline">{events.map((e, i) => (
      <div key={i} className="ev" onClick={() => e.execution_id && api.execution(e.execution_id).then(setDetail).catch(() => {})} style={{ cursor: 'pointer' }}>
        <span className="muted">{new Date(e.timestamp).toLocaleTimeString()}</span> <b>{e.action}</b> <span className="pill">{e.permission || e.status}</span>
        <span className="muted">{e.agent} · {e.resource} · {e.reason?.slice(0, 100)}</span></div>))}
    </div>
    {detail && <pre className="result">{JSON.stringify(detail, null, 2)}</pre>}
  </div>;
}
