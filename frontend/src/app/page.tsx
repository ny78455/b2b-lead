"use client";
import { useEffect, useState } from 'react';
import { fetchLeads } from '../lib/api';
import CompanyTable, { Company } from '../components/CompanyTable';

export default function CRMDashboard() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLeads(page, statusFilter);
      setCompanies(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [page, statusFilter]);

  const statuses = ['', 'new', 'pending', 'enriched', 'drafted', 'sent', 'failed'];

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-end gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-white mb-2">CRM Dashboard</h1>
          <p className="text-gray-400">Manage leads and view enrichment pipeline status.</p>
        </div>

        <div className="flex items-center space-x-3">
          <label className="text-sm text-gray-400">Filter Status:</label>
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded-md focus:ring-blue-500 focus:border-blue-500 block p-2 transition-colors"
          >
            <option value="">All</option>
            {statuses.filter(s => s).map(s => (
              <option key={s} value={s}>{s.toUpperCase()}</option>
            ))}
          </select>
          <button 
            onClick={loadData}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 rounded-md text-sm font-medium transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-md bg-red-900/40 border border-red-800 text-red-400">
          Error loading leads: {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center p-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
        </div>
      ) : (
        <>
          <CompanyTable companies={companies} />
          
          <div className="flex justify-between items-center mt-6">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-md disabled:opacity-50 hover:bg-gray-700 transition-colors text-sm font-medium"
            >
              Previous
            </button>
            <span className="text-gray-400 text-sm">Page {page}</span>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={companies.length < 50}
              className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-md disabled:opacity-50 hover:bg-gray-700 transition-colors text-sm font-medium"
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
