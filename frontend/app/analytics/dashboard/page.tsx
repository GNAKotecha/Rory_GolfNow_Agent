'use client';

import { Suspense, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { WorkflowSuccessRate } from '@/components/analytics/WorkflowSuccessRate';
import { StepFailureAnalysis } from '@/components/analytics/StepFailureAnalysis';
import { PromptVersionComparison } from '@/components/analytics/PromptVersionComparison';

function AnalyticsDashboardContent() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const templateIdStr = searchParams.get('templateId');
  const numericTemplateId = templateIdStr ? parseInt(templateIdStr, 10) : null;

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.push('/login');
    }
  }, [user, authLoading, router]);

  if (authLoading || !user) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <p className="text-gray-600">Loading...</p>
      </div>
    );
  }

  if (!numericTemplateId || Number.isNaN(numericTemplateId)) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <p className="text-gray-600">
          Select a workflow template to view analytics
        </p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-6">
        <header>
          <h1 className="text-2xl font-bold text-gray-900">
            Workflow Analytics Dashboard
          </h1>
          <p className="mt-2 text-sm text-gray-600">
            Monitor workflow performance and optimize prompts based on real data
          </p>
        </header>

        <WorkflowSuccessRate templateId={numericTemplateId} />
        <StepFailureAnalysis templateId={numericTemplateId} />
        <PromptVersionComparison templateId={numericTemplateId} />
      </div>
    </div>
  );
}

export default function AnalyticsDashboardPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-screen bg-gray-50">
          <p className="text-gray-600">Loading...</p>
        </div>
      }
    >
      <AnalyticsDashboardContent />
    </Suspense>
  );
}
