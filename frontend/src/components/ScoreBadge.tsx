// frontend/src/components/ScoreBadge.tsx
import React from 'react';

interface ScoreBadgeProps {
  score: number | null;
  label?: string;
}

export default function ScoreBadge({ score, label }: ScoreBadgeProps) {
  if (score === null || score === undefined) {
    return <span className="text-gray-500 italic text-sm">N/A</span>;
  }

  // Determine color based on score (0-100)
  let colorClass = 'bg-gray-800 text-gray-200 border-gray-700'; // Default low score
  if (score >= 80) {
    colorClass = 'bg-emerald-900/50 text-emerald-400 border-emerald-500/50';
  } else if (score >= 50) {
    colorClass = 'bg-amber-900/50 text-amber-400 border-amber-500/50';
  } else {
    colorClass = 'bg-rose-900/50 text-rose-400 border-rose-500/50';
  }

  return (
    <div className="flex flex-col items-center">
      <div className={`px-3 py-1 rounded-full border shadow-sm flex items-center justify-center font-bold text-sm ${colorClass} transition-all duration-300 hover:scale-105`}>
        {score}
      </div>
      {label && <span className="text-xs text-gray-500 mt-1 uppercase tracking-wider">{label}</span>}
    </div>
  );
}
