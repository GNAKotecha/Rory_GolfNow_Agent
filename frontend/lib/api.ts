const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface LoginResponse {
  access_token: string;
  token_type: string;
}

interface User {
  id: number;
  username: string;
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
}

interface ChatResponse {
  session_id: number;
  message: Message;
  response: Message;
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
      headers['Authorization'] = `Bearer ${this.token}`;
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

  // Auth endpoints
  async login(username: string, password: string): Promise<LoginResponse> {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    const response = await fetch(`${this.baseURL}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData,
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

  // Chat endpoint
  async sendMessage(request: ChatRequest): Promise<ChatResponse> {
    return this.request<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }
}

export const apiClient = new ApiClient();
export type { LoginResponse, User, Session, Message, ChatRequest, ChatResponse };
