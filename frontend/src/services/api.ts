export interface Execution {
  id: string; state: string; agent: string; skill?: string | null;
  user_request: string; result?: string | null; error?: string | null;
  pending_approval_id?: string | null; created_at: string;
}
export interface Approval {
  id: string; execution_id: string; agent: string; tool: string; action: string;
  resource: string; reason: string; risk: string; status: string;
}
export interface Memory { id: string; type: string; content: string; source: string; confidence: number; created_at: string; updated_at: string; last_verified?: string | null; score?: number | null; }
export interface AuditEvent { id?: number | null; timestamp: string; execution_id: string; agent: string; action: string; resource: string; permission: string; reason: string; status: string; duration_ms?: number | null; }
export interface AgentInfo { name: string; description: string; capabilities: string[]; tools: string[]; active: Execution[]; }
export interface SkillInfo { name: string; description: string; version: string; required_tools: string[]; required_permissions: string[]; agent: string; }

const BASE = '';
async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<T>;
}
export const api = {
  command: (message: string) => fetch(`${BASE}/api/command`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message }) }).then(j<Execution & { execution_id: string }>),
  executions: () => fetch(`${BASE}/api/executions`).then(j<Execution[]>),
  execution: (id: string) => fetch(`${BASE}/api/executions/${id}`).then(j<{ execution: Execution; events: AuditEvent[] }>),
  approvals: () => fetch(`${BASE}/api/approvals/pending`).then(j<Approval[]>),
  resolveApproval: (id: string, approved: boolean) => fetch(`${BASE}/api/approvals/${id}/resolve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved }) }).then(j<any>),
  memories: (type?: string) => fetch(`${BASE}/api/memory${type ? `?type=${type}` : ''}`).then(j<Memory[]>),
  searchMemory: (query: string) => fetch(`${BASE}/api/memory/search`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query }) }).then(j<Memory[]>),
  createMemory: (type: string, content: string) => fetch(`${BASE}/api/memory`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type, content }) }).then(j<Memory>),
  deleteMemory: (id: string) => fetch(`${BASE}/api/memory/${id}`, { method: 'DELETE' }).then(j<any>),
  updateMemory: (id: string, content: string) => fetch(`${BASE}/api/memory/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) }).then(j<Memory>),
  relatedMemory: (id: string) => fetch(`${BASE}/api/memory/${id}/related`).then(j<Memory[]>),
  agents: () => fetch(`${BASE}/api/agents`).then(j<AgentInfo[]>),
  skills: () => fetch(`${BASE}/api/skills`).then(j<SkillInfo[]>),
  runSkill: (name: string, input: string) => fetch(`${BASE}/api/skills/${name}/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ input }) }).then(j<any>),
  tools: () => fetch(`${BASE}/api/tools`).then(j<any[]>),
  activity: () => fetch(`${BASE}/api/activity?limit=100`).then(j<AuditEvent[]>),
  models: () => fetch(`${BASE}/api/models`).then(j<{ provider: string; models: Record<string, string>; demo_mode: boolean; status: { provider: string; endpoint: string; model: string; state: string } }>),
  proposals: () => fetch(`${BASE}/api/discovery/proposals`).then(j<any[]>),
  approveProposal: (id: string) => fetch(`${BASE}/api/discovery/${id}/approve`, { method: 'POST' }).then(j<any>)
};
