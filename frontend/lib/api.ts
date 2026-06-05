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
        console.error(`[ApiClient] ${method} ${endpoint} failed:`, errorMsg);
        throw new Error(errorMsg);
      }

      return response.json();
    } catch (error) {
      console.error(`[ApiClient] ${method} ${endpoint} failed:`, error);
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
        console.error('[ApiClient] POST /api/auth/login failed:', errorMsg);
        throw new Error(errorMsg);
      }

      const data = await response.json();
      this.setToken(data.access_token);
      logger.log('[ApiClient] Login successful');
      return data;
    } catch (error) {
      console.error('[ApiClient] POST /api/auth/login failed:', error);
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
};
