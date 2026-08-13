"use client";
import React, { useState } from 'react';
import ScoreBadge from './ScoreBadge';
import StatusChip from './StatusChip';
import {
  deleteLead,
  enrichAndDraftLead,
  getCampaign,
  sendCampaign,
} from '../lib/api';

export interface Company {
  id: string;
  name: string;
  website: string | null;
  industry: string | null;
  rag_score: number | null;
  purchase_score: number | null;
  enrichment_status: string;
  status: string;
  email: string | null;
  updated_at: string;
}

interface Campaign {
  id: string;
  subject: string | null;
  draft_html: string | null;
  status: string;
}

interface CompanyTableProps {
  companies: Company[];
  onLeadDeleted?: () => void;
  onLeadUpdated?: () => void;
}

type RowState = 'idle' | 'enriching' | 'sending';

export default function CompanyTable({ companies, onLeadDeleted, onLeadUpdated }: CompanyTableProps) {
  const [rowStates, setRowStates] = useState<Record<string, RowState>>({});
  const [modal, setModal] = useState<{ company: Company; campaign: Campaign } | null>(null);

  const setRowState = (id: string, state: RowState) =>
    setRowStates(prev => ({ ...prev, [id]: state }));

  const handleEnrich = async (company: Company) => {
    setRowState(company.id, 'enriching');
    try {
      const result = await enrichAndDraftLead(company.id);
      const campaignId = result.campaign_id;
      const campaign = await getCampaign(campaignId);
      setModal({ company, campaign });
      if (onLeadUpdated) onLeadUpdated();
    } catch (err: any) {
      alert(`Enrichment failed for ${company.name}: ${err.message}`);
    } finally {
      setRowState(company.id, 'idle');
    }
  };

  const handleSend = async () => {
    if (!modal) return;
    if (!confirm(`Send email to ${modal.company.email || modal.company.name}?`)) return;
    try {
      await sendCampaign(modal.campaign.id);
      alert('Email sent successfully!');
      setModal(null);
      if (onLeadUpdated) onLeadUpdated();
    } catch (err: any) {
      alert(`Send failed: ${err.message}`);
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Are you sure you want to delete "${name}"?`)) return;
    try {
      await deleteLead(id);
      if (onLeadDeleted) onLeadDeleted();
    } catch (err: any) {
      alert(`Error deleting lead: ${err.message}`);
    }
  };

  if (companies.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-16 bg-gray-900/50 rounded-xl border border-gray-800 backdrop-blur-sm">
        <svg className="w-12 h-12 text-gray-600 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        <p className="text-gray-400 text-lg">No leads found.</p>
        <p className="text-gray-600 text-sm mt-1">Start a campaign to scrape new leads.</p>
      </div>
    );
  }

  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-gray-800 bg-gray-900/50 backdrop-blur-md shadow-2xl">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-gray-800/80 text-gray-400 text-xs uppercase tracking-wider border-b border-gray-700">
              <th className="px-5 py-3.5 font-semibold">Company</th>
              <th className="px-5 py-3.5 font-semibold">Contact</th>
              <th className="px-5 py-3.5 font-semibold text-center">RAG</th>
              <th className="px-5 py-3.5 font-semibold text-center">Buy</th>
              <th className="px-5 py-3.5 font-semibold text-center">Enrichment</th>
              <th className="px-5 py-3.5 font-semibold text-center">Status</th>
              <th className="px-5 py-3.5 font-semibold text-center">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60 text-sm">
            {companies.map((c) => {
              const rowState = rowStates[c.id] || 'idle';
              const isEnriching = rowState === 'enriching';
              return (
                <tr key={c.id} className="hover:bg-gray-800/40 transition-colors group">
                  {/* Company */}
                  <td className="px-5 py-3.5">
                    <div className="font-semibold text-gray-100 group-hover:text-blue-400 transition-colors truncate max-w-[180px]">{c.name}</div>
                    {c.website && (
                      <a href={c.website} target="_blank" rel="noreferrer"
                        className="text-gray-500 hover:text-blue-400 text-xs truncate max-w-[180px] block">
                        {c.website}
                      </a>
                    )}
                    {c.industry && <div className="text-gray-600 text-xs mt-0.5">{c.industry}</div>}
                  </td>

                  {/* Contact */}
                  <td className="px-5 py-3.5">
                    {c.email
                      ? <span className="text-gray-300 text-xs">{c.email}</span>
                      : <span className="text-gray-600 italic text-xs">No email</span>}
                  </td>

                  {/* Scores */}
                  <td className="px-5 py-3.5 text-center"><ScoreBadge score={c.rag_score} /></td>
                  <td className="px-5 py-3.5 text-center"><ScoreBadge score={c.purchase_score} /></td>

                  {/* Enrichment status */}
                  <td className="px-5 py-3.5 text-center"><StatusChip status={c.enrichment_status} /></td>

                  {/* Pipeline status */}
                  <td className="px-5 py-3.5 text-center"><StatusChip status={c.status} /></td>

                  {/* Actions */}
                  <td className="px-5 py-3.5">
                    <div className="flex items-center justify-center gap-1.5">
                      {/* Enrich button */}
                      <button
                        onClick={() => handleEnrich(c)}
                        disabled={isEnriching}
                        title="Enrich lead & generate email"
                        className="flex items-center gap-1 px-2.5 py-1 text-xs font-semibold bg-indigo-600/20 hover:bg-indigo-600/40 border border-indigo-500/50 text-indigo-300 rounded transition-all disabled:opacity-50"
                      >
                        {isEnriching ? (
                          <>
                            <svg className="animate-spin w-3 h-3" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                            </svg>
                            Working…
                          </>
                        ) : '✦ Enrich'}
                      </button>

                      {/* Delete button */}
                      <button
                        onClick={() => handleDelete(c.id, c.name)}
                        title="Delete lead"
                        className="px-2.5 py-1 text-xs font-semibold bg-red-900/20 hover:bg-red-900/40 border border-red-800/50 text-red-400 rounded transition-all"
                      >
                        ✕
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ── Email Preview Modal ──────────────────────────────────────────── */}
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
          onClick={(e) => e.target === e.currentTarget && setModal(null)}>
          <div className="w-full max-w-3xl max-h-[90vh] flex flex-col rounded-2xl border border-gray-700 bg-gray-900 shadow-2xl overflow-hidden">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800 bg-gray-800/60">
              <div>
                <h2 className="text-white font-bold text-lg">Generated Email</h2>
                <p className="text-gray-400 text-sm mt-0.5">
                  To: <span className="text-indigo-300">{modal.company.email || modal.company.name}</span>
                </p>
              </div>
              <button onClick={() => setModal(null)}
                className="text-gray-400 hover:text-white transition-colors text-2xl leading-none">&times;</button>
            </div>

            {/* Subject */}
            {modal.campaign.subject && (
              <div className="px-6 py-3 border-b border-gray-800 bg-gray-800/30">
                <span className="text-gray-500 text-xs uppercase tracking-wider mr-2">Subject</span>
                <span className="text-gray-200 text-sm font-medium">{modal.campaign.subject}</span>
              </div>
            )}

            {/* Email body preview */}
            <div className="flex-1 overflow-y-auto p-6">
              {modal.campaign.draft_html ? (
                <div className="bg-white rounded-lg overflow-hidden">
                  <iframe
                    srcDoc={modal.campaign.draft_html}
                    className="w-full min-h-[400px] border-0"
                    title="Email Preview"
                    sandbox="allow-same-origin"
                  />
                </div>
              ) : (
                <div className="text-gray-500 italic text-center py-12">No email body generated.</div>
              )}
            </div>

            {/* Footer actions */}
            <div className="flex items-center justify-between px-6 py-4 border-t border-gray-800 bg-gray-800/40">
              <div className="flex items-center gap-2">
                <span className={`text-xs px-2 py-1 rounded-full font-semibold ${
                  modal.campaign.status === 'sent' ? 'bg-green-900/50 text-green-400 border border-green-700' :
                  modal.campaign.status === 'approved' ? 'bg-blue-900/50 text-blue-400 border border-blue-700' :
                  'bg-yellow-900/50 text-yellow-400 border border-yellow-700'
                }`}>
                  {modal.campaign.status.replace('_', ' ').toUpperCase()}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <button onClick={() => setModal(null)}
                  className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
                  Close
                </button>
                {modal.campaign.status === 'pending_review' && (
                  <button
                    onClick={handleSend}
                    className="px-5 py-2 text-sm font-semibold bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 text-white rounded-lg transition-all shadow-lg shadow-green-900/30"
                  >
                    ➤ Send Email
                  </button>
                )}
                {modal.campaign.status === 'sent' && (
                  <span className="text-green-400 text-sm font-semibold">✓ Already sent</span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
