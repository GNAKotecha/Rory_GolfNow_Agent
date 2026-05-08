'use client';

import { useEffect, useState } from 'react';
import { analyticsApi, StepFailure } from '@/lib/analytics';

interface Props {
  templateId: number;
}

export function StepFailureAnalysis({ templateId }: Props) {
  const [data, setData] = useState<StepFailure[] | null>(null);
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
      .getStepFailures(templateId)
      .then((result) => {
        if (cancelled) return;
        setData(result);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load step failures');
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
        <p className="text-gray-500">Loading step failures...</p>
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
          Step Failure Analysis
        </h2>
        <p className="text-gray-500">No step execution data available.</p>
      </div>
    );
  }

  const sorted = [...data].sort((a, b) => b.failure_rate - a.failure_rate);

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        Step Failure Analysis
      </h2>
      <div className="space-y-4">
        {sorted.map((step) => {
          const failurePercent = Math.round(step.failure_rate * 100);
          const isHighFailure = step.failure_rate > 0.1;
          const barColor = isHighFailure ? 'bg-red-500' : 'bg-green-500';
          const labelColor = isHighFailure ? 'text-red-700' : 'text-green-700';

          return (
            <div key={step.step_name} className="border-l-4 border-gray-200 pl-4">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-gray-900">
                  {step.step_name}
                </span>
                <span className={`text-sm font-medium ${labelColor}`}>
                  {failurePercent}%
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`${barColor} h-2 rounded-full transition-all`}
                  style={{ width: `${failurePercent}%` }}
                />
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {step.failed_executions} failures out of {step.total_executions}{' '}
                executions
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
