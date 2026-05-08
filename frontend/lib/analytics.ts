const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface WorkflowAnalytics {
  success_rate: number;
  avg_duration_seconds: number | null;
  total_runs: number;
}

export interface StepFailure {
  step_name: string;
  total_executions: number;
  failed_executions: number;
  failure_rate: number;
}

export interface PromptVersionMetrics {
  version_number: number;
  usage_count: number;
  success_count: number;
  success_rate: number;
  avg_latency_ms: number | null;
  is_active: boolean;
  created_at: string;
}

export interface DashboardSummary {
  success_rate: number;
  avg_duration_seconds: number | null;
  step_failures: Record<
    string,
    { total_executions: number; failed_executions: number; failure_rate: number }
  >;
  total_runs: number;
}

async function get<T>(path: string): Promise<T> {
  const token =
    typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const headers: HeadersInit = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}/api${path}`, { headers });
  if (!res.ok) {
    const err = await res
      .json()
      .catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const analyticsApi = {
  getWorkflowSuccessRate: (templateId: number) =>
    get<WorkflowAnalytics>(`/analytics/workflows/${templateId}/success-rate`),
  getStepFailures: (templateId: number) =>
    get<StepFailure[]>(`/analytics/workflows/${templateId}/step-failures`),
  getPromptVersionComparison: (templateId: number) =>
    get<PromptVersionMetrics[]>(
      `/analytics/prompts/${templateId}/version-comparison`
    ),
  getDashboardSummary: (templateId: number) =>
    get<DashboardSummary>(`/analytics/dashboard/${templateId}`),
};
