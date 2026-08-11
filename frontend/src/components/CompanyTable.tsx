"use client";
import React from 'react';
import ScoreBadge from './ScoreBadge';
import StatusChip from './StatusChip';

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

interface CompanyTableProps {
  companies: Company[];
}

export default function CompanyTable({ companies }: CompanyTableProps) {
  if (companies.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-12 bg-gray-900/50 rounded-xl border border-gray-800 backdrop-blur-sm">
        <p className="text-gray-400 text-lg">No leads found.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800 bg-gray-900/50 backdrop-blur-md shadow-2xl">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="bg-gray-800/80 text-gray-400 text-sm uppercase tracking-wider border-b border-gray-700">
            <th className="px-6 py-4 font-semibold">Company</th>
            <th className="px-6 py-4 font-semibold">Contact</th>
            <th className="px-6 py-4 font-semibold text-center">RAG Fit</th>
            <th className="px-6 py-4 font-semibold text-center">Purchase</th>
            <th className="px-6 py-4 font-semibold text-center">Enrichment</th>
            <th className="px-6 py-4 font-semibold text-center">Pipeline</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/60 text-sm">
          {companies.map((c) => (
            <tr key={c.id} className="hover:bg-gray-800/40 transition-colors group">
              <td className="px-6 py-4">
                <div className="font-semibold text-gray-100 group-hover:text-blue-400 transition-colors">{c.name}</div>
                {c.website && (
                  <a href={c.website} target="_blank" rel="noreferrer" className="text-gray-500 hover:text-blue-400 text-xs truncate max-w-[200px] block">
                    {c.website}
                  </a>
                )}
                {c.industry && <div className="text-gray-500 text-xs mt-1">{c.industry}</div>}
              </td>
              <td className="px-6 py-4">
                {c.email ? (
                  <span className="text-gray-300">{c.email}</span>
                ) : (
                  <span className="text-gray-600 italic">No email</span>
                )}
              </td>
              <td className="px-6 py-4 text-center">
                <ScoreBadge score={c.rag_score} />
              </td>
              <td className="px-6 py-4 text-center">
                <ScoreBadge score={c.purchase_score} />
              </td>
              <td className="px-6 py-4 text-center">
                <StatusChip status={c.enrichment_status} />
              </td>
              <td className="px-6 py-4 text-center">
                <StatusChip status={c.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
