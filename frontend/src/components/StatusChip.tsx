// frontend/src/components/StatusChip.tsx
import React from 'react';

interface StatusChipProps {
  status: string;
}

export default function StatusChip({ status }: StatusChipProps) {
  let colorClass = 'bg-gray-800 text-gray-300 border-gray-700'; // fallback
  let display = status.replace('_', ' ').toUpperCase();

  switch (status.toLowerCase()) {
    case 'new':
      colorClass = 'bg-blue-900/40 text-blue-400 border-blue-500/30';
      break;
    case 'pending':
    case 'pending_review':
      colorClass = 'bg-yellow-900/40 text-yellow-400 border-yellow-500/30';
      break;
    case 'enriched':
    case 'drafted':
      colorClass = 'bg-purple-900/40 text-purple-400 border-purple-500/30';
      break;
    case 'approved':
    case 'sent':
    case 'done':
      colorClass = 'bg-emerald-900/40 text-emerald-400 border-emerald-500/30';
      break;
    case 'failed':
    case 'rejected':
      colorClass = 'bg-red-900/40 text-red-400 border-red-500/30';
      break;
  }

  return (
    <span className={`px-2 py-1 text-xs font-semibold rounded-md border shadow-sm ${colorClass}`}>
      {display}
    </span>
  );
}
