const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface LoginResponse {
  access_token: string;
  token_type: string;
}

interface User {
  id: number;
  name: string;
  email: string;
  role: string;
}

interface Session {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

interface Message {
  id: number;
  session_id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

interface ChatRequest {
  session_id?: number;
  message: string;
  model?: string;
  allow_opus?: boolean;
  opus_justification?: string;
}

interface ChatResponse {
  session_id: number;
  message: Message;
  response: Message;
}

interface ModelOption {
  id: string;
  label: string;
  provider: string;
  tier: string;
}

interface ModelListResponse {
  options: ModelOption[];
  default_model: string;
  provider: string;
  policy_note?: string;
}

// Trace types
interface TraceFilters {
  trace_id?: string;
  user_id?: string;
  session_id?: string;
  name?: string;
  status?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}

interface TracePreview {
  trace_id: string;
  user_id: string | null;
  session_id: string | null;
  name: string | null;
  status: string;
  created_at: string;
  duration_ms: number | null;
  input_preview: string | null;
  output_preview: string | null;
}

interface TraceListResponse {
  traces: TracePreview[];
  total: number;
  limit: number;
  offset: number;
}

interface ObservationDetail {
  id: string;
  type: string;
  name: string | null;
  start_time: string;
  end_time: string | null;
  input: any;
  output: any;
  metadata: any;
}

interface TraceDetail {
  trace_id: string;
  user_id: string | null;
  session_id: string | null;
  name: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  duration_ms: number | null;
  input: any;
  output: any;
  metadata: any;
  observations: ObservationDetail[];
}

// Test result types
interface TestResultFilters {
  scenario_name?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

interface TestResult {
  id: number;
  test_run_id: number;
  scenario_name: string;
  status: string;
  duration_seconds: number | null;
  error_message: string | null;
  trace_id: string | null;
  created_at: string;
}

interface TestResultListResponse {
  results: TestResult[];
  total: number;
  limit: number;
  offset: number;
}

// Integration management types
interface TenantMCPIntegration {
  id: number;
  tenant_id: number;
  integration_name: string;
  auth_type: 'oauth' | 'api_key' | 'pat';
  config: Record<string, any>;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface TenantMCPIntegrationCreate {
  integration_name: string;
  auth_type: 'oauth' | 'api_key' | 'pat';
  config?: Record<string, any>;
}

interface HealthCheckResponse {
  status: 'healthy' | 'unhealthy' | 'unknown';
  message: string;
  timestamp: string;
}

interface OAuthInitiateResponse {
  authorizationUrl: string;
  state: string;
}

interface MCPToolSchema {
  name: string;
  description: string;
  inputSchema: Record<string, any>;
}

// Skills management types
interface TenantSkill {
  id: number;
  tenant_id: number;
  skill_name: string;
  description: string;
  skill_data: Record<string, any>;
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  created_by: number;
}

interface TenantSkillCreate {
  skill_name: string;
  description: string;
  skill_data: Record<string, any>;
}

interface TenantSkillUpdate extends Partial<TenantSkillCreate> {
  is_active?: boolean;
}

interface SkillListResponse {
  skills: TenantSkill[];
  total: number;
  limit: number;
  offset: number;
}

class ApiClient {
  private baseURL: string;
  private token: string | null = null;

  constructor() {
    this.baseURL = API_URL;

    // Load token from localStorage if available
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('access_token');
    }
  }

  setToken(token: string) {
    this.token = token;
    if (typeof window !== 'undefined') {
      localStorage.setItem('access_token', token);
    }
  }

  clearToken() {
    this.token = null;
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
    }
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (this.token) {
      (headers as Record<string, string>)['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${this.baseURL}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP error! status: ${response.status}`);
    }

    return response.json();
  }

  /**
   * Wrapper for API calls with consistent error handling
   */
  private async apiCall<T>(
    endpoint: string,
    options: RequestInit = {},
    errorMessage: string
  ): Promise<T> {
    try {
      return await this.request<T>(endpoint, options);
    } catch (error) {
      throw new Error(
        error instanceof Error ? error.message : errorMessage
      );
    }
  }

  // Auth endpoints
  async login(email: string, password: string): Promise<LoginResponse> {
    const response = await fetch(`${this.baseURL}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(error.detail || 'Login failed');
    }

    const data = await response.json();
    this.setToken(data.access_token);
    return data;
  }

  async getCurrentUser(): Promise<User> {
    return this.request<User>('/api/auth/me');
  }

  logout() {
    this.clearToken();
  }

  // Session endpoints
  async getSessions(): Promise<Session[]> {
    return this.request<Session[]>('/api/sessions');
  }

  async createSession(title?: string): Promise<Session> {
    return this.request<Session>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ title: title || 'New Chat' }),
    });
  }

  async getSessionMessages(sessionId: number): Promise<Message[]> {
    return this.request<Message[]>(`/api/sessions/${sessionId}/messages`);
  }

  async updateSession(sessionId: number, title: string): Promise<Session> {
    return this.request<Session>(`/api/sessions/${sessionId}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    });
  }

  async abortSession(sessionId: number, runId: string): Promise<{ status: string; run_id: string }> {
    return this.request<{ status: string; run_id: string }>(`/api/sessions/${sessionId}/abort`, {
      method: 'POST',
      body: JSON.stringify({ run_id: runId }),
    });
  }

  // Chat endpoint
  async sendMessage(request: ChatRequest): Promise<ChatResponse> {
    return this.request<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getChatModels(): Promise<ModelListResponse> {
    return this.request<ModelListResponse>('/api/chat/models');
  }

  // Admin trace endpoints
  async getTraces(filters: TraceFilters = {}): Promise<TraceListResponse> {
    const params = new URLSearchParams();

    if (filters.trace_id) params.append('trace_id', filters.trace_id);
    if (filters.user_id) params.append('user_id', filters.user_id);
    if (filters.session_id) params.append('session_id', filters.session_id);
    if (filters.name) params.append('name', filters.name);
    if (filters.status) params.append('status', filters.status);
    if (filters.start_date) params.append('start_date', filters.start_date);
    if (filters.end_date) params.append('end_date', filters.end_date);
    if (filters.limit) params.append('limit', filters.limit.toString());
    if (filters.offset) params.append('offset', filters.offset.toString());

    const queryString = params.toString();
    const endpoint = `/api/admin/traces${queryString ? `?${queryString}` : ''}`;

    return this.request<TraceListResponse>(endpoint);
  }

  async getTrace(traceId: string): Promise<TraceDetail> {
    return this.request<TraceDetail>(`/api/admin/traces/${traceId}`);
  }

  async getTestResults(filters: TestResultFilters = {}): Promise<TestResultListResponse> {
    const params = new URLSearchParams();

    if (filters.scenario_name) params.append('scenario_name', filters.scenario_name);
    if (filters.status) params.append('status', filters.status);
    if (filters.limit) params.append('limit', filters.limit.toString());
    if (filters.offset) params.append('offset', filters.offset.toString());

    const queryString = params.toString();
    const endpoint = `/api/admin/test-results${queryString ? `?${queryString}` : ''}`;

    return this.request<TestResultListResponse>(endpoint);
  }

  // Integration management endpoints
  async getIntegrations(): Promise<TenantMCPIntegration[]> {
    return this.apiCall<TenantMCPIntegration[]>(
      '/api/integrations',
      {},
      'Failed to fetch integrations'
    );
  }

  async getIntegration(id: number): Promise<TenantMCPIntegration> {
    return this.apiCall<TenantMCPIntegration>(
      `/api/integrations/${id}`,
      {},
      `Failed to fetch integration ${id}`
    );
  }

  async createIntegration(
    data: TenantMCPIntegrationCreate
  ): Promise<TenantMCPIntegration> {
    return this.apiCall<TenantMCPIntegration>(
      '/api/integrations',
      {
        method: 'POST',
        body: JSON.stringify(data),
      },
      'Failed to create integration'
    );
  }

  async updateIntegration(
    id: number,
    data: Partial<TenantMCPIntegration>
  ): Promise<TenantMCPIntegration> {
    return this.apiCall<TenantMCPIntegration>(
      `/api/integrations/${id}`,
      {
        method: 'PATCH',
        body: JSON.stringify(data),
      },
      `Failed to update integration ${id}`
    );
  }

  async deleteIntegration(id: number): Promise<void> {
    await this.apiCall<void>(
      `/api/integrations/${id}`,
      { method: 'DELETE' },
      `Failed to delete integration ${id}`
    );
  }

  async enableIntegration(id: number): Promise<TenantMCPIntegration> {
    return this.apiCall<TenantMCPIntegration>(
      `/api/integrations/${id}/enable`,
      { method: 'POST' },
      `Failed to enable integration ${id}`
    );
  }

  async disableIntegration(id: number): Promise<TenantMCPIntegration> {
    return this.apiCall<TenantMCPIntegration>(
      `/api/integrations/${id}/disable`,
      { method: 'POST' },
      `Failed to disable integration ${id}`
    );
  }

  async testIntegrationHealth(id: number): Promise<HealthCheckResponse> {
    return this.apiCall<HealthCheckResponse>(
      `/api/integrations/${id}/health`,
      { method: 'POST' },
      `Failed to check integration health ${id}`
    );
  }

  async testConnection(id: number): Promise<HealthCheckResponse> {
    return this.apiCall<HealthCheckResponse>(
      `/api/integrations/${id}/test`,
      { method: 'POST' },
      `Failed to test integration connection ${id}`
    );
  }

  async storeApiKey(
    integrationId: number,
    apiKey: string,
    baseUrl?: string
  ): Promise<void> {
    const body: Record<string, any> = { api_key: apiKey };
    if (baseUrl) {
      body.base_url = baseUrl;
    }

    await this.apiCall<void>(
      `/api/integrations/${integrationId}/credentials/api-key`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
      `Failed to store API key for integration ${integrationId}`
    );
  }

  async storePAT(
    integrationId: number,
    token: string,
    baseUrl?: string
  ): Promise<void> {
    const body: Record<string, any> = { token };
    if (baseUrl) {
      body.base_url = baseUrl;
    }

    await this.apiCall<void>(
      `/api/integrations/${integrationId}/credentials/pat`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
      `Failed to store PAT for integration ${integrationId}`
    );
  }

  async initiateOAuth(integrationId: number): Promise<OAuthInitiateResponse> {
    return this.apiCall<OAuthInitiateResponse>(
      `/api/integrations/${integrationId}/oauth/initiate`,
      { method: 'POST' },
      `Failed to initiate OAuth for integration ${integrationId}`
    );
  }

  async completeOAuthCallback(
    integrationId: number,
    code: string,
    state: string
  ): Promise<TenantMCPIntegration> {
    return this.apiCall<TenantMCPIntegration>(
      `/api/integrations/${integrationId}/oauth/callback`,
      {
        method: 'POST',
        body: JSON.stringify({ code, state }),
      },
      `Failed to complete OAuth for integration ${integrationId}`
    );
  }

  async listAvailableTools(): Promise<MCPToolSchema[]> {
    return this.apiCall<MCPToolSchema[]>(
      '/api/integrations/tools',
      {},
      'Failed to list available tools'
    );
  }

  // Skills management endpoints
  async getSkills(limit?: number, offset?: number): Promise<SkillListResponse> {
    const params = new URLSearchParams();
    if (limit) params.append('limit', limit.toString());
    if (offset) params.append('offset', offset.toString());

    const queryString = params.toString();
    const endpoint = `/api/skills${queryString ? `?${queryString}` : ''}`;

    return this.apiCall<SkillListResponse>(endpoint, {}, 'Failed to fetch skills');
  }

  async getSkill(id: number): Promise<TenantSkill> {
    return this.apiCall<TenantSkill>(
      `/api/skills/${id}`,
      {},
      `Failed to fetch skill ${id}`
    );
  }

  async createSkill(data: TenantSkillCreate): Promise<TenantSkill> {
    return this.apiCall<TenantSkill>(
      '/api/skills',
      {
        method: 'POST',
        body: JSON.stringify(data),
      },
      'Failed to create skill'
    );
  }

  async updateSkill(id: number, data: TenantSkillUpdate): Promise<TenantSkill> {
    return this.apiCall<TenantSkill>(
      `/api/skills/${id}`,
      {
        method: 'PATCH',
        body: JSON.stringify(data),
      },
      `Failed to update skill ${id}`
    );
  }

  async deleteSkill(id: number): Promise<void> {
    await this.apiCall<void>(
      `/api/skills/${id}`,
      { method: 'DELETE' },
      `Failed to delete skill ${id}`
    );
  }

  async activateSkill(id: number): Promise<TenantSkill> {
    return this.apiCall<TenantSkill>(
      `/api/skills/${id}/activate`,
      { method: 'POST' },
      `Failed to activate skill ${id}`
    );
  }

  async deactivateSkill(id: number): Promise<TenantSkill> {
    return this.apiCall<TenantSkill>(
      `/api/skills/${id}/deactivate`,
      { method: 'POST' },
      `Failed to deactivate skill ${id}`
    );
  }

  // Workflows management endpoints
  async getWorkflows(limit?: number, offset?: number): Promise<any> {
    const params = new URLSearchParams();
    if (limit) params.append('limit', limit.toString());
    if (offset) params.append('offset', offset.toString());

    const queryString = params.toString();
    const endpoint = `/api/workflows${queryString ? `?${queryString}` : ''}`;

    return this.apiCall<any>(endpoint, {}, 'Failed to fetch workflows');
  }

  async getWorkflow(id: number): Promise<any> {
    return this.apiCall<any>(
      `/api/workflows/${id}`,
      {},
      `Failed to fetch workflow ${id}`
    );
  }

  async createWorkflow(data: any): Promise<any> {
    return this.apiCall<any>(
      '/api/workflows',
      {
        method: 'POST',
        body: JSON.stringify(data),
      },
      'Failed to create workflow'
    );
  }

  async updateWorkflow(id: number, data: any): Promise<any> {
    return this.apiCall<any>(
      `/api/workflows/${id}`,
      {
        method: 'PATCH',
        body: JSON.stringify(data),
      },
      `Failed to update workflow ${id}`
    );
  }

  async deleteWorkflow(id: number): Promise<void> {
    await this.apiCall<void>(
      `/api/workflows/${id}`,
      { method: 'DELETE' },
      `Failed to delete workflow ${id}`
    );
  }

  async activateWorkflow(id: number): Promise<any> {
    return this.apiCall<any>(
      `/api/workflows/${id}/activate`,
      { method: 'POST' },
      `Failed to activate workflow ${id}`
    );
  }

  async deactivateWorkflow(id: number): Promise<any> {
    return this.apiCall<any>(
      `/api/workflows/${id}/deactivate`,
      { method: 'POST' },
      `Failed to deactivate workflow ${id}`
    );
  }
}

export const apiClient = new ApiClient();
export type {
  LoginResponse,
  User,
  Session,
  Message,
  ChatRequest,
  ChatResponse,
  ModelOption,
  ModelListResponse,
  TraceFilters,
  TracePreview,
  TraceListResponse,
  TraceDetail,
  ObservationDetail,
  TestResultFilters,
  TestResult,
  TestResultListResponse,
  TenantMCPIntegration,
  TenantMCPIntegrationCreate,
  HealthCheckResponse,
  OAuthInitiateResponse,
  MCPToolSchema,
  TenantSkill,
  TenantSkillCreate,
  TenantSkillUpdate,
  SkillListResponse,
};
