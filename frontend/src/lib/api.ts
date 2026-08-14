// frontend/lib/api.ts

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

export async function fetchLeads(page = 1, status = '') {
  const params = new URLSearchParams({ page: page.toString() });
  if (status) params.append('status', status);

  const res = await fetch(`${API_BASE_URL}/leads?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch leads');
  return res.json();
}

export async function deleteLead(id: string) {
  const res = await fetch(`${API_BASE_URL}/leads/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete lead');
  return res.json();
}

export async function deleteAllLeads() {
  const res = await fetch(`${API_BASE_URL}/leads`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete all leads');
  return res.json();
}

export async function enrichLead(companyId: string) {
  const res = await fetch(`${API_BASE_URL}/enrich/${companyId}`, {
    method: 'POST',
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || 'Enrichment failed');
  }
  return res.json();
}

export async function enrichAndDraftLead(companyId: string) {
  const res = await fetch(`${API_BASE_URL}/enrich/${companyId}/draft`, {
    method: 'POST',
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || 'Enrichment + draft failed');
  }
  return res.json(); // returns { campaign_id, ... }
}

export async function getCampaign(campaignId: string) {
  const res = await fetch(`${API_BASE_URL}/campaigns/${campaignId}`);
  if (!res.ok) throw new Error('Failed to fetch campaign');
  return res.json();
}

export async function sendCampaign(campaignId: string) {
  const res = await fetch(`${API_BASE_URL}/campaigns/${campaignId}/approve`, {
    method: 'PUT',
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || 'Failed to send email');
  }
  return res.json();
}

export async function enrichAllLeads() {
  const res = await fetch(`${API_BASE_URL}/bulk/enrich-all`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to start enrich all');
  return res.json();
}

export async function sendAllLeads() {
  const res = await fetch(`${API_BASE_URL}/bulk/send-all`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to start send all');
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

export const startScraping = async (queries: string[], targetLeads?: number) => {
  const payload: any = { queries };
  if (targetLeads !== undefined) {
    payload.target_leads = targetLeads;
  }
  const res = await fetch(`${API_BASE_URL}/scrape`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to start scraping');
  return res.json();
};

export const fetchQueries = async (): Promise<string[]> => {
  const res = await fetch(`${API_BASE_URL}/scrape/queries`);
  if (!res.ok) throw new Error('Failed to load queries');
  const data = await res.json();
  return data.queries || [];
};

export async function startBulkSending() {
  const res = await fetch(`${API_BASE_URL}/bulk/send`, {
    method: 'POST',
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to start bulk sending');
  }
  return res.json();
}

export async function stopScraping() {
  const res = await fetch(`${API_BASE_URL}/scrape/stop`, {
    method: 'POST',
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to stop scraping');
  }
  return res.json();
}

export async function startAutomate(queries: string[], targetLeads: number) {
  const res = await fetch(`${API_BASE_URL}/bulk/automate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ queries, target_leads: targetLeads }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to start automation flow');
  }
  return res.json();
}
