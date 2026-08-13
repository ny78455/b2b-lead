"use client";
import { useEffect, useState } from 'react';
import { fetchLeads, startScraping, startBulkSending, stopScraping } from '../lib/api';
import CompanyTable, { Company } from '../components/CompanyTable';

export default function CRMDashboard() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [scrapeQuery, setScrapeQuery] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

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

  const handleStartCampaign = async () => {
    if (!scrapeQuery.trim()) {
      alert("Please enter a search query (e.g. Plumbers in Austin, TX)");
      return;
    }
    setActionLoading(true);
    try {
      await startScraping([scrapeQuery.trim()]);
      alert("Campaign started! Scraping runs in the background. Refresh the page later to see new leads.");
      setScrapeQuery('');
    } catch (err: any) {
      alert(`Error starting campaign: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleStopCampaign = async () => {
    setActionLoading(true);
    try {
      await stopScraping();
      alert("Stop signal sent! Scraping will halt shortly.");
    } catch (err: any) {
      alert(`Error stopping campaign: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleStartSendingMail = async () => {
    if (!confirm("This will automatically write and send emails to ALL pending new/enriched leads. Proceed?")) return;
    
    setActionLoading(true);
    try {
      await startBulkSending();
      alert("Bulk sending started in the background. Check back in a few minutes.");
      setTimeout(loadData, 2000);
    } catch (err: any) {
      alert(`Error starting bulk send: ${err.message}`);
    } finally {
      setActionLoading(false);
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

      <div className="bg-gray-800 p-4 rounded-lg border border-gray-700 flex flex-col sm:flex-row items-center gap-4">
        <div className="flex-1 flex gap-2 w-full">
          <input 
            type="text" 
            placeholder="Search query (e.g., Plumbers in NY)" 
            value={scrapeQuery}
            onChange={e => setScrapeQuery(e.target.value)}
            className="flex-1 bg-gray-900 border border-gray-700 text-white rounded-md px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
          <button 
            onClick={handleStartCampaign}
            disabled={actionLoading}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-md text-sm font-medium transition-colors whitespace-nowrap"
          >
            Start Campaign
          </button>
          <button 
            onClick={handleStopCampaign}
            disabled={actionLoading}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white rounded-md text-sm font-medium transition-colors whitespace-nowrap"
          >
            Stop Campaign
          </button>
        </div>
        <div className="hidden sm:block w-px h-8 bg-gray-700"></div>
        <button 
          onClick={handleStartSendingMail}
          disabled={actionLoading}
          className="w-full sm:w-auto px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded-md text-sm font-medium transition-colors whitespace-nowrap"
        >
          Start Sending Mail
        </button>
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
          <CompanyTable companies={companies} onLeadDeleted={loadData} />
          
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
