'use client';

import { useEffect, useState } from 'react';
import { analyticsApi, WorkflowAnalytics } from '@/lib/analytics';

const SECONDS_PER_MINUTE = 60;

interface Props {
  templateId: number;
}

export function WorkflowSuccessRate({ templateId }: Props) {
  const [data, setData] = useState<WorkflowAnalytics | null>(null);
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
      .getWorkflowSuccessRate(templateId)
      .then((result) => {
        if (cancelled) return;
        setData(result);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load metrics');
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
        <p className="text-gray-500">Loading metrics...</p>
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

  if (!data) {
    return null;
  }

  const successPercent = Math.round(data.success_rate * 100);
  const avgDurationMinutes =
    data.avg_duration_seconds !== null
      ? (data.avg_duration_seconds / SECONDS_PER_MINUTE).toFixed(1)
      : null;

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        Workflow Performance
      </h2>
      <div
        role="status"
        aria-label="Workflow performance summary"
        className="grid grid-cols-1 md:grid-cols-3 gap-4"
      >
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="text-sm text-green-700 font-medium">Success Rate</div>
          <p
            aria-label={`Success rate: ${successPercent} percent`}
            className="text-3xl font-bold text-green-900 mt-1"
          >
            {successPercent}%
          </p>
        </div>
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="text-sm text-blue-700 font-medium">Avg Duration</div>
          <p
            aria-label={
              avgDurationMinutes !== null
                ? `Average duration: ${avgDurationMinutes} minutes`
                : 'Average duration: not available'
            }
            className="text-3xl font-bold text-blue-900 mt-1"
          >
            {avgDurationMinutes !== null ? `${avgDurationMinutes}m` : 'N/A'}
          </p>
        </div>
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <div className="text-sm text-gray-700 font-medium">Total Runs</div>
          <p
            aria-label={`Total runs: ${data.total_runs}`}
            className="text-3xl font-bold text-gray-900 mt-1"
          >
            {data.total_runs}
          </p>
        </div>
      </div>
    </div>
  );
}
