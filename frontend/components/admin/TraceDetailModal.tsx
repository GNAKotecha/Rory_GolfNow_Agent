'use client';

import { useState } from 'react';
import { TraceDetail } from '@/lib/api';

interface TraceDetailModalProps {
  trace: TraceDetail | null;
  onClose: () => void;
  loading: boolean;
}

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

const formatJSON = (obj: any): string => {
  return JSON.stringify(obj, null, 2);
};

const truncateString = (str: string, length: number = 200): string => {
  if (str.length <= length) return str;
  return str.substring(0, length) + '...';
};

const STATUS_COLORS: Record<string, { bg: string; text: string; badge: string }> = {
  success: { bg: 'bg-green-50', text: 'text-green-800', badge: 'bg-green-100' },
  error: { bg: 'bg-red-50', text: 'text-red-800', badge: 'bg-red-100' },
  timeout: { bg: 'bg-yellow-50', text: 'text-yellow-800', badge: 'bg-yellow-100' },
  validation_error: { bg: 'bg-orange-50', text: 'text-orange-800', badge: 'bg-orange-100' },
};

export default function TraceDetailModal({
  trace,
  onClose,
  loading,
}: TraceDetailModalProps) {
  const [showFullJSON, setShowFullJSON] = useState(false);
  const [expandedSpans, setExpandedSpans] = useState<Set<string>>(new Set());

  if (!trace) return null;

  const statusColors = STATUS_COLORS[trace.status] || {
    bg: 'bg-gray-50',
    text: 'text-gray-800',
    badge: 'bg-gray-100',
  };

  const toggleSpan = (spanId: string) => {
    const newExpanded = new Set(expandedSpans);
    if (newExpanded.has(spanId)) {
      newExpanded.delete(spanId);
    } else {
      newExpanded.add(spanId);
    }
    setExpandedSpans(newExpanded);
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-lg shadow-2xl max-w-4xl w-full my-8">
        {/* Header */}
        <div className={`px-6 py-4 border-b border-gray-200 flex justify-between items-start ${statusColors.bg}`}>
          <div>
            <h2 className="text-xl font-bold text-gray-900">Trace Details</h2>
            <p className="mt-1 text-sm text-gray-600 font-mono break-all">
              {trace.trace_id}
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={loading}
            className="text-gray-400 hover:text-gray-600 disabled:opacity-50"
          >
            <svg
              className="h-6 w-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="px-6 py-4 overflow-y-auto max-h-96">
          {/* Summary Section */}
          <div className="mb-6 p-4 bg-gray-50 rounded-lg">
            <h3 className="font-semibold text-gray-900 mb-4">Summary</h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-gray-600">Status</p>
                <p className="font-medium">
                  <span
                    className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${statusColors.badge} ${statusColors.text}`}
                  >
                    {trace.status}
                  </span>
                </p>
              </div>
              <div>
                <p className="text-gray-600">Duration</p>
                <p className="font-medium">{formatDuration(trace.duration_ms)}</p>
              </div>
              <div>
                <p className="text-gray-600">Created</p>
                <p className="font-medium text-xs">{formatDate(trace.created_at)}</p>
              </div>
              <div>
                <p className="text-gray-600">Updated</p>
                <p className="font-medium text-xs">{formatDate(trace.updated_at)}</p>
              </div>
              {trace.user_id && (
                <div>
                  <p className="text-gray-600">User ID</p>
                  <p className="font-medium">{trace.user_id}</p>
                </div>
              )}
              {trace.session_id && (
                <div>
                  <p className="text-gray-600">Session ID</p>
                  <p className="font-medium text-xs break-all">{trace.session_id}</p>
                </div>
              )}
              {trace.name && (
                <div className="col-span-2">
                  <p className="text-gray-600">Workflow Name</p>
                  <p className="font-medium">{trace.name}</p>
                </div>
              )}
            </div>
          </div>

          {/* Spans/Observations Section */}
          {trace.observations && trace.observations.length > 0 && (
            <div className="mb-6">
              <h3 className="font-semibold text-gray-900 mb-3">Execution Timeline</h3>
              <div className="space-y-2">
                {trace.observations.map((span) => (
                  <div
                    key={span.id}
                    className="border border-gray-200 rounded-lg overflow-hidden"
                  >
                    <button
                      onClick={() => toggleSpan(span.id)}
                      className="w-full px-4 py-3 bg-gray-50 hover:bg-gray-100 text-left font-medium text-gray-900 flex justify-between items-center"
                    >
                      <div>
                        <p className="text-sm">{span.name || span.type}</p>
                        <p className="text-xs text-gray-600 font-normal">
                          {formatDuration(
                            span.end_time
                              ? new Date(span.end_time).getTime() -
                                  new Date(span.start_time).getTime()
                              : null
                          )}
                        </p>
                      </div>
                      <svg
                        className={`h-4 w-4 text-gray-600 transition-transform ${
                          expandedSpans.has(span.id) ? 'transform rotate-180' : ''
                        }`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 14l-7 7m0 0l-7-7m7 7V3"
                        />
                      </svg>
                    </button>

                    {expandedSpans.has(span.id) && (
                      <div className="px-4 py-3 bg-white border-t border-gray-200 text-xs font-mono text-gray-700 space-y-2">
                        {span.input && (
                          <div>
                            <p className="font-semibold text-gray-900 mb-1">Input:</p>
                            <pre className="bg-gray-50 p-2 rounded overflow-x-auto max-h-40 overflow-y-auto whitespace-pre-wrap break-words">
                              {formatJSON(span.input)}
                            </pre>
                          </div>
                        )}
                        {span.output && (
                          <div>
                            <p className="font-semibold text-gray-900 mb-1">Output:</p>
                            <pre className="bg-gray-50 p-2 rounded overflow-x-auto max-h-40 overflow-y-auto whitespace-pre-wrap break-words">
                              {formatJSON(span.output)}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Full JSON Toggle */}
          <div className="mb-6">
            <button
              onClick={() => setShowFullJSON(!showFullJSON)}
              className="text-blue-600 hover:text-blue-800 font-medium text-sm"
            >
              {showFullJSON ? 'Hide' : 'Show'} Full JSON
            </button>

            {showFullJSON && (
              <div className="mt-3 p-4 bg-gray-50 rounded-lg">
                <pre className="text-xs font-mono text-gray-700 overflow-x-auto max-h-80 overflow-y-auto whitespace-pre-wrap break-words">
                  {formatJSON(trace)}
                </pre>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex justify-between">
          <button
            onClick={() => copyToClipboard(trace.trace_id)}
            className="text-blue-600 hover:text-blue-800 font-medium text-sm"
          >
            Copy Trace ID
          </button>
          <button
            onClick={onClose}
            disabled={loading}
            className="px-4 py-2 bg-gray-700 text-white rounded-md hover:bg-gray-800 disabled:opacity-50 font-medium text-sm"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
