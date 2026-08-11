"use client";
import { useEffect, useState } from 'react';
import { fetchReplies } from '@/lib/api';
import StatusChip from '@/components/StatusChip';

export default function RepliesInbox() {
  const [replies, setReplies] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadReplies = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchReplies();
      setReplies(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReplies();
  }, []);

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-white mb-2">Inbox</h1>
          <p className="text-gray-400">Classified replies from your outreach campaigns.</p>
        </div>
        <button 
          onClick={loadReplies}
          className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 rounded-md text-sm font-medium transition-colors"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-md bg-red-900/40 border border-red-800 text-red-400">
          Error loading replies: {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center p-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
        </div>
      ) : replies.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-16 bg-gray-900/50 rounded-xl border border-gray-800 backdrop-blur-sm">
          <p className="text-gray-400 text-lg">No replies received yet.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-800 bg-gray-900/50 backdrop-blur-md shadow-2xl">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-gray-800/80 text-gray-400 text-sm uppercase tracking-wider border-b border-gray-700">
                <th className="px-6 py-4 font-semibold">Date</th>
                <th className="px-6 py-4 font-semibold">Company</th>
                <th className="px-6 py-4 font-semibold">From</th>
                <th className="px-6 py-4 font-semibold">Classification</th>
                <th className="px-6 py-4 font-semibold">Sentiment</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60 text-sm">
              {replies.map((r) => (
                <tr key={r.id} className="hover:bg-gray-800/40 transition-colors">
                  <td className="px-6 py-4 text-gray-400 whitespace-nowrap">
                    {new Date(r.received_at).toLocaleDateString()} {new Date(r.received_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </td>
                  <td className="px-6 py-4 font-medium text-gray-200">
                    {r.company_name || 'Unknown'}
                  </td>
                  <td className="px-6 py-4 text-gray-400">
                    {r.from_email}
                  </td>
                  <td className="px-6 py-4">
                    <StatusChip status={r.classification} />
                  </td>
                  <td className="px-6 py-4 capitalize text-gray-300">
                    <span className={`inline-flex items-center space-x-1 ${
                      r.sentiment === 'positive' ? 'text-emerald-400' :
                      r.sentiment === 'negative' ? 'text-red-400' :
                      'text-gray-400'
                    }`}>
                      {r.sentiment === 'positive' && <span>👍</span>}
                      {r.sentiment === 'negative' && <span>👎</span>}
                      {r.sentiment === 'neutral' && <span>😐</span>}
                      <span>{r.sentiment}</span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
