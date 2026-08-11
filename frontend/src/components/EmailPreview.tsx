"use client";
import React, { useState } from 'react';
import { editCampaign, approveCampaign, rejectCampaign } from '../lib/api';

interface EmailPreviewProps {
  campaign: {
    id: string;
    subject: string | null;
    draft_html: string | null;
  };
  onActionComplete: () => void;
}

export default function EmailPreview({ campaign, onActionComplete }: EmailPreviewProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [subject, setSubject] = useState(campaign.subject || '');
  const [html, setHtml] = useState(campaign.draft_html || '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    setLoading(true);
    setError(null);
    try {
      await editCampaign(campaign.id, html, subject);
      setIsEditing(false);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!window.confirm("Are you sure you want to approve and send this email?")) return;
    setLoading(true);
    setError(null);
    try {
      await approveCampaign(campaign.id);
      onActionComplete();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    if (!window.confirm("Reject this draft?")) return;
    setLoading(true);
    setError(null);
    try {
      await rejectCampaign(campaign.id);
      onActionComplete();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full rounded-xl border border-gray-800 bg-gray-900 overflow-hidden shadow-2xl">
      {/* Header / Actions */}
      <div className="bg-gray-800/80 p-4 border-b border-gray-700 flex justify-between items-center backdrop-blur-md">
        <h3 className="font-semibold text-gray-200">Email Draft Review</h3>
        <div className="flex space-x-3">
          {isEditing ? (
            <button
              onClick={handleSave}
              disabled={loading}
              className="px-4 py-1.5 text-sm font-medium rounded-md bg-blue-600 hover:bg-blue-500 text-white transition-colors"
            >
              {loading ? 'Saving...' : 'Save Changes'}
            </button>
          ) : (
            <button
              onClick={() => setIsEditing(true)}
              disabled={loading}
              className="px-4 py-1.5 text-sm font-medium rounded-md bg-gray-700 hover:bg-gray-600 text-gray-200 transition-colors"
            >
              Edit
            </button>
          )}
          
          <button
            onClick={handleReject}
            disabled={loading}
            className="px-4 py-1.5 text-sm font-medium rounded-md bg-gray-700 text-red-400 hover:bg-gray-600 hover:text-red-300 transition-colors"
          >
            Reject
          </button>
          
          <button
            onClick={handleApprove}
            disabled={loading}
            className="px-4 py-1.5 text-sm font-medium rounded-md bg-emerald-600 hover:bg-emerald-500 text-white shadow-[0_0_15px_rgba(5,150,105,0.4)] transition-all hover:shadow-[0_0_20px_rgba(5,150,105,0.6)]"
          >
            {loading ? 'Sending...' : 'Approve & Send'}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-900/50 text-red-300 text-sm border-b border-red-800">
          Error: {error}
        </div>
      )}

      {/* Editor / Preview Body */}
      <div className="flex-1 flex flex-col p-4 space-y-4 overflow-y-auto">
        <div className="space-y-1">
          <label className="text-xs text-gray-400 font-semibold uppercase tracking-wider">Subject</label>
          {isEditing ? (
            <input
              type="text"
              value={subject}
              onChange={e => setSubject(e.target.value)}
              className="w-full bg-gray-950 border border-gray-700 rounded-md p-2 text-gray-200 focus:outline-none focus:border-blue-500 transition-colors"
            />
          ) : (
            <div className="font-medium text-gray-200">{subject}</div>
          )}
        </div>

        <div className="flex-1 flex flex-col space-y-1">
          <label className="text-xs text-gray-400 font-semibold uppercase tracking-wider">Body</label>
          {isEditing ? (
            <textarea
              value={html}
              onChange={e => setHtml(e.target.value)}
              className="flex-1 w-full bg-gray-950 border border-gray-700 rounded-md p-3 text-gray-300 font-mono text-sm focus:outline-none focus:border-blue-500 transition-colors resize-none"
            />
          ) : (
            <div className="flex-1 bg-white rounded-md p-6 text-gray-900 overflow-y-auto border border-gray-700/50 shadow-inner">
              <div dangerouslySetInnerHTML={{ __html: html }} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
