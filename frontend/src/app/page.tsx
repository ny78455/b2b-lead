import { useEffect, useState } from 'react';
import { fetchLeads, startScraping, startBulkSending, stopScraping, enrichAllLeads, sendAllLeads, deleteAllLeads, fetchQueries, startAutomate, fetchProgress, AutomationProgress } from '../lib/api';
import CompanyTable, { Company } from '../components/CompanyTable';

export default function CRMDashboard() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [scrapeQuery, setScrapeQuery] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [targetLeads, setTargetLeads] = useState<number>(1000);
  const [loadedQueries, setLoadedQueries] = useState<string[]>([]);
  const [progress, setProgress] = useState<AutomationProgress | null>(null);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    const pollProgress = async () => {
      try {
        const data = await fetchProgress();
        setProgress(data);
      } catch (err) {
        console.error("Failed to fetch progress", err);
      }
    };
    
    pollProgress(); // initial poll
    interval = setInterval(pollProgress, 5000); // poll every 5s

    return () => clearInterval(interval);
  }, []);

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

  const handleFetchQueries = async () => {
    try {
      const queries = await fetchQueries();
      setLoadedQueries(queries);
      alert(`Loaded ${queries.length} queries successfully.`);
    } catch (err: any) {
      alert(`Error loading queries: ${err.message}`);
    }
  };

  const handleStartBulkCampaign = async () => {
    if (loadedQueries.length === 0) {
      alert("Please fetch queries first.");
      return;
    }
    setActionLoading(true);
    try {
      await startScraping(loadedQueries, targetLeads);
      alert(`Bulk campaign started for ${targetLeads} target leads using ${loadedQueries.length} queries.`);
    } catch (err: any) {
      alert(`Error starting bulk campaign: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleStartAutomate = async () => {
    if (loadedQueries.length === 0) {
      alert("Please fetch queries first.");
      return;
    }
    if (!confirm("⚠️ This will scrape, enrich, draft, and SEND emails fully automatically.\n\nOnce completed, ALL LEADS will be deleted from the database and the Google Sheet will be cleared.\n\nAre you sure you want to run this full automation?")) {
      return;
    }
    setActionLoading(true);
    try {
      await startAutomate(loadedQueries, targetLeads);
      alert(`Full automated pipeline started for ${targetLeads} target leads!\n\nThis will take a while. Sit back and relax.`);
    } catch (err: any) {
      alert(`Error starting automation: ${err.message}`);
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

  const handleEnrichAll = async () => {
    if (!confirm('Enrich ALL new leads in the background? This may take a few minutes.')) return;
    setActionLoading(true);
    try {
      await enrichAllLeads();
      alert('Enrichment started for all new leads in the background.');
    } catch (err: any) {
      alert(`Error: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSendAll = async () => {
    if (!confirm('Send emails to ALL enriched leads? This bypasses per-lead review.')) return;
    setActionLoading(true);
    try {
      await sendAllLeads();
      alert('Sending started for all enriched leads in the background.');
      setTimeout(loadData, 3000);
    } catch (err: any) {
      alert(`Error: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteAll = async () => {
    if (!confirm('⚠️ Delete ALL leads? This cannot be undone.')) return;
    if (!confirm('Are you absolutely sure? ALL data will be lost.')) return;
    setActionLoading(true);
    try {
      const result = await deleteAllLeads();
      alert(`Deleted ${result.count} leads.`);
      loadData();
    } catch (err: any) {
      alert(`Error: ${err.message}`);
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

      {/* Bulk Queries Section */}
      <div className="bg-gray-800 p-4 rounded-lg border border-gray-700 flex flex-col sm:flex-row items-center gap-4">
        <div className="flex-1 flex gap-2 w-full items-center">
          <span className="text-gray-400 text-sm font-medium whitespace-nowrap">Bulk Scraping:</span>
          <button 
            onClick={handleFetchQueries}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-md text-sm font-medium transition-colors whitespace-nowrap"
          >
            Fetch Queries {loadedQueries.length > 0 && `(${loadedQueries.length})`}
          </button>
          <div className="flex items-center space-x-2">
            <label className="text-sm text-gray-400 whitespace-nowrap">Target Leads:</label>
            <input 
              type="number"
              value={targetLeads}
              onChange={e => setTargetLeads(Number(e.target.value))}
              className="w-24 bg-gray-900 border border-gray-700 text-white rounded-md px-2 py-1.5 text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <button 
            onClick={handleStartBulkCampaign}
            disabled={actionLoading || loadedQueries.length === 0}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-md text-sm font-medium transition-colors whitespace-nowrap"
          >
            Start Bulk Campaign
          </button>
          <button 
            onClick={handleStartAutomate}
            disabled={actionLoading || loadedQueries.length === 0}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-md text-sm font-medium transition-colors whitespace-nowrap shadow-lg shadow-purple-500/30"
          >
            ✨ Start Automate
          </button>
        </div>
      </div>

      {/* Progress Tracker UI */}
      {progress && progress.is_running && (
        <div className="bg-gray-800 p-4 rounded-lg border border-purple-500 shadow-md shadow-purple-900/20">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-bold text-purple-400 flex items-center gap-2">
              <span className="animate-pulse">⚡</span> Automation Running
            </h3>
            <span className="text-xs font-semibold px-2 py-1 bg-gray-900 rounded-full text-gray-300 capitalize border border-gray-700">
              Stage: {progress.current_stage}
            </span>
          </div>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-gray-400">Leads Generated</span>
                <span className="font-medium text-white">{progress.leads_generated} / {progress.target_leads || '?'}</span>
              </div>
              <div className="w-full bg-gray-900 rounded-full h-2">
                <div 
                  className="bg-blue-500 h-2 rounded-full transition-all duration-500" 
                  style={{ width: `${progress.target_leads ? Math.min(100, (progress.leads_generated / progress.target_leads) * 100) : 0}%` }}
                ></div>
              </div>
            </div>
            
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-gray-400">Emails Sent</span>
                <span className="font-medium text-white">{progress.emails_sent} / {progress.target_leads || '?'}</span>
              </div>
              <div className="w-full bg-gray-900 rounded-full h-2">
                <div 
                  className="bg-green-500 h-2 rounded-full transition-all duration-500" 
                  style={{ width: `${progress.target_leads ? Math.min(100, (progress.emails_sent / progress.target_leads) * 100) : 0}%` }}
                ></div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Batch actions */}
      <div className="flex flex-wrap items-center gap-2 p-3 bg-gray-800/50 rounded-lg border border-gray-700">
        <span className="text-gray-400 text-xs font-semibold uppercase tracking-wider mr-1">Batch:</span>
        <button
          onClick={handleEnrichAll}
          disabled={actionLoading}
          className="px-3 py-1.5 text-xs font-semibold bg-indigo-600/20 hover:bg-indigo-600/40 border border-indigo-500/50 text-indigo-300 rounded-md transition-all disabled:opacity-50"
        >
          ✦ Enrich All
        </button>
        <button
          onClick={handleSendAll}
          disabled={actionLoading}
          className="px-3 py-1.5 text-xs font-semibold bg-green-600/20 hover:bg-green-600/40 border border-green-500/50 text-green-300 rounded-md transition-all disabled:opacity-50"
        >
          ➤ Send All
        </button>
        <button
          onClick={handleDeleteAll}
          disabled={actionLoading}
          className="px-3 py-1.5 text-xs font-semibold bg-red-600/20 hover:bg-red-600/40 border border-red-500/50 text-red-400 rounded-md transition-all disabled:opacity-50"
        >
          ✕ Delete All
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
          <CompanyTable companies={companies} onLeadDeleted={loadData} onLeadUpdated={loadData} />
          
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
