"use client";
import { useEffect, useState } from 'react';
import { fetchPendingCampaigns } from '@/lib/api';
import EmailPreview from '@/components/EmailPreview';
import ScoreBadge from '@/components/ScoreBadge';

export default function ReviewQueue() {
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCampaigns = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPendingCampaigns();
      setCampaigns(data);
      if (data.length > 0 && !selectedId) {
        setSelectedId(data[0].id);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCampaigns();
  }, []);

  const handleActionComplete = () => {
    // Remove the processed campaign and select the next one
    setCampaigns(prev => {
      const filtered = prev.filter(c => c.id !== selectedId);
      if (filtered.length > 0) {
        setSelectedId(filtered[0].id);
      } else {
        setSelectedId(null);
      }
      return filtered;
    });
  };

  const selectedCampaign = campaigns.find(c => c.id === selectedId);

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] animate-in fade-in duration-500">
      <div className="mb-6">
        <h1 className="text-3xl font-extrabold tracking-tight text-white mb-2">Review Queue</h1>
        <p className="text-gray-400">Human-in-the-loop approval gate. No email is sent until you approve it here.</p>
      </div>

      {error && (
        <div className="p-4 mb-4 rounded-md bg-red-900/40 border border-red-800 text-red-400">
          Error loading campaigns: {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center p-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
        </div>
      ) : campaigns.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-16 bg-gray-900/50 rounded-xl border border-gray-800 backdrop-blur-sm flex-1">
          <div className="text-4xl mb-4">🎉</div>
          <p className="text-gray-300 text-xl font-medium">Inbox Zero!</p>
          <p className="text-gray-500 mt-2">No pending emails to review.</p>
          <button onClick={loadCampaigns} className="mt-6 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-md transition-colors">
            Refresh
          </button>
        </div>
      ) : (
        <div className="flex flex-1 gap-6 overflow-hidden">
          {/* Left Panel: List of pending campaigns */}
          <div className="w-1/3 flex flex-col rounded-xl border border-gray-800 bg-gray-900/50 overflow-hidden shadow-xl backdrop-blur-md">
            <div className="p-4 border-b border-gray-800 bg-gray-800/50 flex justify-between items-center">
              <h2 className="font-semibold text-gray-200">Pending ({campaigns.length})</h2>
              <button onClick={loadCampaigns} className="text-xs text-blue-400 hover:text-blue-300">Refresh</button>
            </div>
            <div className="flex-1 overflow-y-auto divide-y divide-gray-800/60">
              {campaigns.map(c => (
                <button
                  key={c.id}
                  onClick={() => setSelectedId(c.id)}
                  className={`w-full text-left p-4 hover:bg-gray-800/60 transition-colors ${selectedId === c.id ? 'bg-gray-800/80 border-l-4 border-blue-500' : 'border-l-4 border-transparent'}`}
                >
                  <div className="flex justify-between items-start mb-1">
                    <span className="font-semibold text-gray-200 truncate">{c.company_name}</span>
                    <span className="text-xs text-gray-500">{new Date(c.created_at).toLocaleDateString()}</span>
                  </div>
                  <div className="text-sm text-gray-400 truncate mb-3">{c.contact_email || 'No email'}</div>
                  <div className="flex space-x-4">
                    <ScoreBadge score={c.rag_score} label="RAG" />
                    <ScoreBadge score={c.purchase_score} label="Intent" />
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Right Panel: Selected campaign preview */}
          <div className="w-2/3">
            {selectedCampaign ? (
              <EmailPreview 
                campaign={selectedCampaign} 
                onActionComplete={handleActionComplete} 
              />
            ) : (
              <div className="h-full flex items-center justify-center bg-gray-900/50 rounded-xl border border-gray-800">
                <p className="text-gray-500">Select a campaign to review.</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
