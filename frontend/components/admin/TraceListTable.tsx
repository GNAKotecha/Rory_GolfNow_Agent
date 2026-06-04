'use client';

import { TracePreview } from '@/lib/api';

interface TraceListTableProps {
  traces: TracePreview[];
  onViewTrace: (traceId: string) => void;
  loading: boolean;
}

const STATUS_COLORS: Record<string, { bg: string; text: string; badge: string }> = {
  success: { bg: 'bg-green-50', text: 'text-green-800', badge: 'bg-green-100' },
  error: { bg: 'bg-red-50', text: 'text-red-800', badge: 'bg-red-100' },
  timeout: { bg: 'bg-yellow-50', text: 'text-yellow-800', badge: 'bg-yellow-100' },
  validation_error: { bg: 'bg-orange-50', text: 'text-orange-800', badge: 'bg-orange-100' },
};

const formatDate = (dateString: string): string => {
  const date = new Date(dateString);
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

const formatDuration = (ms: number | null): string => {
  if (ms === null) return 'N/A';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

export default function TraceListTable({
  traces,
  onViewTrace,
  loading,
}: TraceListTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50">
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Trace ID
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              User ID
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Status
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Created
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Duration
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Action
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {traces.map((trace) => {
            const statusColors = STATUS_COLORS[trace.status] || {
              bg: 'bg-gray-50',
              text: 'text-gray-800',
              badge: 'bg-gray-100',
            };

            return (
              <tr key={trace.trace_id} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap">
                  <code className="text-xs bg-gray-100 px-2 py-1 rounded text-gray-800">
                    {trace.trace_id.substring(0, 12)}...
                  </code>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                  {trace.user_id ? (
                    <span>{trace.user_id}</span>
                  ) : (
                    <span className="text-gray-400">—</span>
                  )}
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span
                    className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${statusColors.badge} ${statusColors.text}`}
                  >
                    {trace.status}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                  {formatDate(trace.created_at)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                  {formatDuration(trace.duration_ms)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  <button
                    onClick={() => onViewTrace(trace.trace_id)}
                    disabled={loading}
                    className="text-blue-600 hover:text-blue-800 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    View
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
