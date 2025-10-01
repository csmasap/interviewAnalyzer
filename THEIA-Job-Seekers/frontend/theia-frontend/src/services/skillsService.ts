export type SkillRecord = {
  name: string;
  score: number; // 1..10
  source: 'THEIA_Interview__c' | 'TR1__Opportunity_Discussed__c';
  created_at?: string; // ISO date
};
import { loadApiBase } from './apiBase';

function authHeaders(): Record<string, string> {
  try {
    const t = localStorage.getItem('THEIA_TOKEN') || '';
    return t ? { Authorization: `Bearer ${t}` } : {};
  } catch (_e) {
    return {};
  }
}

export async function fetchSkills(): Promise<SkillRecord[]> {
  const API_BASE = await loadApiBase();
  let url = `${API_BASE}/api/v1/skills`;
  try {
    const cid = localStorage.getItem('THEIA_CONTACT_ID');
    if (cid) url += `?contact_id=${encodeURIComponent(cid)}`;
  } catch (_e) {}
  const resp = await fetch(url, { headers: { ...authHeaders() } });
  if (!resp.ok) return [];
  const data = await resp.json();
  if (data && Array.isArray(data.skills)) return data.skills as SkillRecord[];
  return [];
}


