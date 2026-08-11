// frontend/lib/api.ts

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

export async function fetchLeads(page = 1, status = '') {
  const params = new URLSearchParams({ page: page.toString() });
  if (status) params.append('status', status);

  const res = await fetch(`${API_BASE_URL}/leads?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch leads');
  return res.json();
}

export async function fetchPendingCampaigns() {
  const res = await fetch(`${API_BASE_URL}/campaigns/pending`);
  if (!res.ok) throw new Error('Failed to fetch campaigns');
  return res.json();
}

export async function fetchCampaign(id: string) {
  const res = await fetch(`${API_BASE_URL}/campaigns/${id}`);
  if (!res.ok) throw new Error('Failed to fetch campaign details');
  return res.json();
}

export async function approveCampaign(id: string) {
  const res = await fetch(`${API_BASE_URL}/campaigns/${id}/approve`, {
    method: 'PUT',
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to approve and send campaign');
  }
  return res.json();
}

export async function rejectCampaign(id: string) {
  const res = await fetch(`${API_BASE_URL}/campaigns/${id}/reject`, {
    method: 'PUT',
  });
  if (!res.ok) throw new Error('Failed to reject campaign');
  return res.json();
}

export async function editCampaign(id: string, html: string, subject?: string) {
  const res = await fetch(`${API_BASE_URL}/campaigns/${id}/edit`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ draft_html: html, subject }),
  });
  if (!res.ok) throw new Error('Failed to save campaign edit');
  return res.json();
}

export async function fetchReplies() {
  const res = await fetch(`${API_BASE_URL}/replies`);
  if (!res.ok) throw new Error('Failed to fetch replies');
  return res.json();
}
