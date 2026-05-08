'use client';

import { useEffect, useState } from 'react';
import { analyticsApi, WorkflowAnalytics } from '@/lib/analytics';

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
      ? (data.avg_duration_seconds / 60).toFixed(1)
      : null;

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        Workflow Performance
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="text-sm text-green-700 font-medium">Success Rate</div>
          <div className="text-3xl font-bold text-green-900 mt-1">
            {successPercent}%
          </div>
        </div>
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="text-sm text-blue-700 font-medium">Avg Duration</div>
          <div className="text-3xl font-bold text-blue-900 mt-1">
            {avgDurationMinutes !== null ? `${avgDurationMinutes}m` : 'N/A'}
          </div>
        </div>
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <div className="text-sm text-gray-700 font-medium">Total Runs</div>
          <div className="text-3xl font-bold text-gray-900 mt-1">
            {data.total_runs}
          </div>
        </div>
      </div>
    </div>
  );
}
