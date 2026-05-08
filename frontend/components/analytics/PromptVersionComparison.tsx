'use client';

import { useEffect, useState } from 'react';
import { analyticsApi, PromptVersionMetrics } from '@/lib/analytics';

interface Props {
  templateId: number;
}

export function PromptVersionComparison({ templateId }: Props) {
  const [data, setData] = useState<PromptVersionMetrics[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTemplateId, setActiveTemplateId] = useState(templateId);

  // Reset state when templateId changes (React 19 "derived state" pattern)
  if (templateId !== activeTemplateId) {
    setActiveTemplateId(templateId);
    setData(null);
    setError(null);
    setLoading(true);
  }

  useEffect(() => {
    let cancelled = false;

    analyticsApi
      .getPromptVersionComparison(templateId)
      .then((result) => {
        if (cancelled) return;
        setData(result);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(
          err instanceof Error ? err.message : 'Failed to load prompt versions'
        );
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [templateId]);

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <p className="text-gray-500">Loading prompt versions...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <p className="text-red-600">Error: {error}</p>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Prompt Version Comparison
        </h2>
        <p className="text-gray-500">No prompt versions available.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        Prompt Version Comparison
      </h2>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead>
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Version
              </th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Usage
              </th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Success Rate
              </th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Avg Latency
              </th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {data.map((version) => {
              const successPercent = Math.round(version.success_rate * 100);
              const successColor =
                version.success_rate > 0.8
                  ? 'text-green-700'
                  : 'text-yellow-700';
              const rowClass = version.is_active ? 'bg-blue-50' : '';
              const avgLatency =
                version.avg_latency_ms !== null
                  ? `${Math.round(version.avg_latency_ms)} ms`
                  : 'N/A';

              return (
                <tr key={version.version_number} className={rowClass}>
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">
                    v{version.version_number}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">
                    {version.usage_count}
                  </td>
                  <td
                    className={`px-4 py-3 text-sm font-medium ${successColor}`}
                  >
                    {successPercent}%
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">
                    {avgLatency}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {version.is_active ? (
                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        Active
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
                        Inactive
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
