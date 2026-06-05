import { logger } from './logger';

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

interface TenantSkill {
  id: number;
  tenant_id: number;
  skill_name: string;
  description: string | null;
  skill_data: Record<string, any>;
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  created_by: number | null;
}

interface TenantSkillCreate {
  skill_name: string;
  description?: string | null;
  skill_data: Record<string, any>;
}

interface TenantSkillUpdate {
  description?: string | null;
  skill_data?: Record<string, any>;
  is_active?: boolean;
}

interface SkillsListResponse {
  skills: TenantSkill[];
  total?: number;
}

interface TenantMCPIntegration {
  id: number;
  tenant_id: number;
  integration_name: string;
  auth_type: string;
  config: Record<string, any>;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface TenantMCPIntegrationCreate {
  integration_name: string;
  auth_type: string;
  config?: Record<string, any>;
}

interface TenantMCPIntegrationUpdate {
  integration_name?: string;
  config?: Record<string, any>;
  is_enabled?: boolean;
}

interface HealthCheckResponse {
  status: string;
  integration_id: number;
  integration_name: string;
  is_enabled: boolean;
  checked_at: string;
}

interface TracePreview {
  trace_id: string;
  user_id?: string | null;
  session_id?: string | null;
  name?: string | null;
  status?: string | null;
  created_at: string;
  updated_at?: string | null;
  duration_ms?: number | null;
  input_preview?: string | null;
  output_preview?: string | null;
  tags?: string[];
}

interface SpanDetail {
  span_id: string;
  trace_id: string;
  parent_span_id?: string | null;
  name: string;
  start_time: string;
  end_time?: string | null;
  duration_ms?: number | null;
  status?: string | null;
  input?: Record<string, any> | null;
  output?: Record<string, any> | null;
  metadata?: Record<string, any> | null;
  level?: string | null;
}

interface TraceDetail {
  trace_id: string;
  user_id?: string | null;
  session_id?: string | null;
  name?: string | null;
  status?: string | null;
  created_at: string;
  updated_at?: string | null;
  duration_ms?: number | null;
  input?: Record<string, any> | null;
  output?: Record<string, any> | null;
  metadata?: Record<string, any> | null;
  tags?: string[];
  observations?: SpanDetail[];
}

interface TraceListResponse {
  traces: TracePreview[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

interface TenantWorkflow {
  id: number;
  tenant_id: number;
  workflow_name: string;
  description: string | null;
  workflow_definition: Record<string, any>;
  version: number;
  is_active: boolean;
  active_version: number | null;
  created_at: string;
  updated_at: string;
  created_by: number | null;
}

interface TenantWorkflowCreate {
  workflow_name: string;
  description?: string | null;
  workflow_definition: Record<string, any>;
}

interface TenantWorkflowUpdate {
  description?: string | null;
  workflow_definition?: Record<string, any>;
  is_active?: boolean;
  active_version?: number | null;
}

interface WorkflowsListResponse {
  workflows: TenantWorkflow[];
  total?: number;
}

// Type aliases for convenience
type Workflow = TenantWorkflow;
type Skill = TenantSkill;

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

  hasToken(): boolean {
    return this.token !== null;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const method = options.method || 'GET';
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (this.token) {
      (headers as Record<string, string>)['Authorization'] = `Bearer ${this.token}`;
    }

    logger.debug(`[ApiClient] ${method} ${endpoint}`);

    try {
      const response = await fetch(`${this.baseURL}${endpoint}`, {
        ...options,
        headers,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        const errorMsg = error.detail || `HTTP error! status: ${response.status}`;
        logger.error(`[ApiClient] ${method} ${endpoint} failed:`, errorMsg);
        throw new Error(errorMsg);
      }

      return response.json();
    } catch (error) {
      logger.error(`[ApiClient] ${method} ${endpoint} failed:`, error);
      throw error;
    }
  }

  // Auth endpoints
  async login(email: string, password: string): Promise<LoginResponse> {
    logger.debug('[ApiClient] POST /api/auth/login');

    try {
      const response = await fetch(`${this.baseURL}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Login failed' }));
        const errorMsg = error.detail || 'Login failed';
        logger.error('[ApiClient] POST /api/auth/login failed:', errorMsg);
        throw new Error(errorMsg);
      }

      const data = await response.json();
      this.setToken(data.access_token);
      logger.log('[ApiClient] Login successful');
      return data;
    } catch (error) {
      logger.error('[ApiClient] POST /api/auth/login failed:', error);
      throw error;
    }
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

  // MCP Integration endpoints
  async getIntegrations(): Promise<TenantMCPIntegration[]> {
    return this.request<TenantMCPIntegration[]>('/api/integrations');
  }

  async getIntegration(integrationId: number): Promise<TenantMCPIntegration> {
    return this.request<TenantMCPIntegration>(`/api/integrations/${integrationId}`);
  }

  async createIntegration(data: TenantMCPIntegrationCreate): Promise<TenantMCPIntegration> {
    return this.request<TenantMCPIntegration>('/api/integrations', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateIntegration(integrationId: number, data: TenantMCPIntegrationUpdate): Promise<TenantMCPIntegration> {
    return this.request<TenantMCPIntegration>(`/api/integrations/${integrationId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteIntegration(integrationId: number): Promise<void> {
    await this.request<void>(`/api/integrations/${integrationId}`, {
      method: 'DELETE',
    });
  }

  async enableIntegration(integrationId: number): Promise<TenantMCPIntegration> {
    return this.request<TenantMCPIntegration>(`/api/integrations/${integrationId}/enable`, {
      method: 'POST',
    });
  }

  async disableIntegration(integrationId: number): Promise<TenantMCPIntegration> {
    return this.request<TenantMCPIntegration>(`/api/integrations/${integrationId}/disable`, {
      method: 'POST',
    });
  }

  async checkIntegrationHealth(integrationId: number): Promise<HealthCheckResponse> {
    return this.request<HealthCheckResponse>(`/api/integrations/${integrationId}/health`, {
      method: 'POST',
    });
  }

  async storeApiKey(integrationId: number, apiKey: string, baseUrl?: string): Promise<any> {
    return this.request(`/api/integrations/${integrationId}/credentials/api-key`, {
      method: 'POST',
      body: JSON.stringify({
        api_key: apiKey,
        metadata: baseUrl ? { base_url: baseUrl } : {},
      }),
    });
  }

  async storePAT(integrationId: number, pat: string, baseUrl?: string): Promise<any> {
    return this.request(`/api/integrations/${integrationId}/credentials/pat`, {
      method: 'POST',
      body: JSON.stringify({
        pat: pat,
        metadata: baseUrl ? { base_url: baseUrl } : {},
      }),
    });
  }

  async initiateOAuth(integrationId: number): Promise<{ authorizationUrl: string; state: string }> {
    const response = await this.request<{ authorization_url: string; state: string }>(`/api/integrations/${integrationId}/oauth/initiate`, {
      method: 'POST',
    });
    return {
      authorizationUrl: response.authorization_url,
      state: response.state,
    };
  }

  async completeOAuthCallback(integrationId: number, code: string, state: string): Promise<any> {
    return this.request(`/api/integrations/${integrationId}/oauth/callback?code=${code}&state=${state}`);
  }

  async testConnection(integrationId: number): Promise<HealthCheckResponse> {
    return this.checkIntegrationHealth(integrationId);
  }

  // Traces endpoints
  async getTraces(limit: number = 50, offset: number = 0): Promise<TraceListResponse> {
    const params = new URLSearchParams();
    params.append('limit', limit.toString());
    params.append('offset', offset.toString());
    return this.request<TraceListResponse>(`/api/admin/traces?${params.toString()}`);
  }

  async getTrace(traceId: string): Promise<TraceDetail> {
    return this.request<TraceDetail>(`/api/admin/traces/${traceId}`);
  }

  async getTraceSpans(traceId: string): Promise<SpanDetail[]> {
    return this.request<SpanDetail[]>(`/api/admin/traces/${traceId}/spans`);
  }

  async searchTraces(filters: {
    user_id?: string;
    session_id?: string;
    name?: string;
    status?: string;
    start_date?: string;
    end_date?: string;
    tags?: string[];
    limit?: number;
    offset?: number;
  }): Promise<TraceListResponse> {
    return this.request<TraceListResponse>('/api/admin/traces/search', {
      method: 'POST',
      body: JSON.stringify(filters),
    });
  }

  // Skills endpoints
  async getSkills(limit?: number, offset?: number, activeOnly: boolean = false): Promise<SkillsListResponse> {
    const params = new URLSearchParams();
    if (activeOnly) {
      params.append('active_only', 'true');
    }
    const queryString = params.toString();
    const endpoint = `/api/skills${queryString ? `?${queryString}` : ''}`;

    const response = await this.request<{ skills: TenantSkill[] }>(endpoint);

    // Add total count (frontend can use this for pagination)
    return {
      skills: response.skills,
      total: response.skills.length,
    };
  }

  async getSkill(skillId: number): Promise<TenantSkill> {
    return this.request<TenantSkill>(`/api/skills/${skillId}`);
  }

  async createSkill(data: TenantSkillCreate): Promise<TenantSkill> {
    return this.request<TenantSkill>('/api/skills', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateSkill(skillId: number, data: TenantSkillUpdate): Promise<TenantSkill> {
    return this.request<TenantSkill>(`/api/skills/${skillId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteSkill(skillId: number): Promise<void> {
    await this.request<void>(`/api/skills/${skillId}`, {
      method: 'DELETE',
    });
  }

  async activateSkill(skillId: number): Promise<TenantSkill> {
    return this.request<TenantSkill>(`/api/skills/${skillId}/activate`, {
      method: 'POST',
    });
  }

  async deactivateSkill(skillId: number): Promise<TenantSkill> {
    return this.request<TenantSkill>(`/api/skills/${skillId}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: false }),
    });
  }

  // Workflows endpoints
  async getWorkflows(limit?: number, offset?: number, activeOnly: boolean = false): Promise<WorkflowsListResponse> {
    const params = new URLSearchParams();
    if (activeOnly) {
      params.append('active_only', 'true');
    }
    const queryString = params.toString();
    const endpoint = `/api/workflows${queryString ? `?${queryString}` : ''}`;

    const response = await this.request<{ workflows: TenantWorkflow[] }>(endpoint);

    return {
      workflows: response.workflows,
      total: response.workflows.length,
    };
  }

  async getWorkflow(workflowId: number): Promise<TenantWorkflow> {
    return this.request<TenantWorkflow>(`/api/workflows/${workflowId}`);
  }

  async createWorkflow(data: TenantWorkflowCreate): Promise<TenantWorkflow> {
    return this.request<TenantWorkflow>('/api/workflows', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateWorkflow(workflowId: number, data: TenantWorkflowUpdate): Promise<TenantWorkflow> {
    return this.request<TenantWorkflow>(`/api/workflows/${workflowId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteWorkflow(workflowId: number): Promise<void> {
    await this.request<void>(`/api/workflows/${workflowId}`, {
      method: 'DELETE',
    });
  }

  async activateWorkflow(workflowId: number): Promise<TenantWorkflow> {
    return this.request<TenantWorkflow>(`/api/workflows/${workflowId}/activate`, {
      method: 'POST',
    });
  }

  async deactivateWorkflow(workflowId: number): Promise<TenantWorkflow> {
    return this.request<TenantWorkflow>(`/api/workflows/${workflowId}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: false }),
    });
  }

  // Skill invocation endpoints
  async invokeSkill(skillName: string, context: Record<string, any> = {}): Promise<{
    success: boolean;
    skill_name: string;
    message: string;
    context: Record<string, any>;
  }> {
    return this.request('/api/skills/invoke', {
      method: 'POST',
      body: JSON.stringify({
        skill_name: skillName,
        context,
      }),
    });
  }

  async matchSkill(userMessage: string): Promise<{ matched: boolean; skill: TenantSkill | null }> {
    return this.request('/api/skills/match', {
      method: 'POST',
      body: JSON.stringify({ user_message: userMessage }),
    });
  }

  async abortSession(sessionId: number, runId: string): Promise<void> {
    return this.request(`/api/sessions/${sessionId}/abort`, {
      method: 'POST',
      body: JSON.stringify({ run_id: runId }),
    });
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
  TenantSkill,
  TenantSkillCreate,
  TenantSkillUpdate,
  SkillsListResponse,
  TenantMCPIntegration,
  TenantMCPIntegrationCreate,
  TenantMCPIntegrationUpdate,
  HealthCheckResponse,
  TracePreview,
  TraceDetail,
  SpanDetail,
  TraceListResponse,
  TenantWorkflow,
  TenantWorkflowCreate,
  TenantWorkflowUpdate,
  WorkflowsListResponse,
  Workflow,
  Skill,
};
