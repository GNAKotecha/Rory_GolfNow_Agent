const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ==================== Type Definitions ====================

export interface TraceFilter {
  trace_id?: string;
  user_id?: string;
  session_id?: string;
  name?: string;
  status?: 'success' | 'error' | 'timeout' | 'validation_error';
  start_date?: string;  // ISO datetime
  end_date?: string;
  limit?: number;
  offset?: number;
}

export interface TracePreview {
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

export interface TraceSpan {
  id: string;
  type: string;
  name: string | null;
  start_time: string;
  end_time: string | null;
  input: Record<string, any> | null;
  output: Record<string, any> | null;
  metadata: Record<string, any> | null;
}

export interface TraceDetail {
  trace_id: string;
  user_id: string | null;
  session_id: string | null;
  name: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  duration_ms: number | null;
  input: Record<string, any> | null;
  output: Record<string, any> | null;
  metadata: Record<string, any> | null;
  observations: TraceSpan[];
}

export interface TraceListResponse {
  traces: TracePreview[];
  total: number;
  limit: number;
  offset: number;
}

export interface TestResultFilter {
  scenario_name?: string;
  status?: 'passed' | 'failed' | 'error';
  limit?: number;
  offset?: number;
}

export interface TestResult {
  id: number;
  test_run_id: number;
  scenario_name: string;
  status: string;
  duration_seconds: number | null;
  error_message: string | null;
  trace_id: string | null;
  created_at: string;
}

export interface TestResultsResponse {
  results: TestResult[];
  total: number;
  limit: number;
  offset: number;
}

// ==================== Traces API Client ====================

class TracesApiClient {
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
  }

  /**
   * Internal request helper method
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    // Add token to request headers
    if (this.token) {
      (headers as Record<string, string>)['Authorization'] = `Bearer ${this.token}`;
    } else if (typeof window !== 'undefined') {
      // Try to load from localStorage if not in memory
      const storedToken = localStorage.getItem('access_token');
      if (storedToken) {
        (headers as Record<string, string>)['Authorization'] = `Bearer ${storedToken}`;
      }
    }

    const response = await fetch(`${this.baseURL}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorMessage = `HTTP error! status: ${response.status}`;
      try {
        const error = await response.json();
        errorMessage = error.detail || error.message || errorMessage;
      } catch {
        // If response is not JSON, use default message
      }

      // Handle specific error cases
      if (response.status === 401) {
        throw new Error('Unauthorized: Admin access required');
      }
      if (response.status === 404) {
        throw new Error(`Not found: ${errorMessage}`);
      }

      throw new Error(errorMessage);
    }

    return response.json();
  }

  /**
   * List traces with optional filters and pagination
   */
  async getTraces(filters: TraceFilter = {}): Promise<TraceListResponse> {
    const params = new URLSearchParams();

    if (filters.trace_id) params.append('trace_id', filters.trace_id);
    if (filters.user_id) params.append('user_id', filters.user_id);
    if (filters.session_id) params.append('session_id', filters.session_id);
    if (filters.name) params.append('name', filters.name);
    if (filters.status) params.append('status', filters.status);
    if (filters.start_date) params.append('start_date', filters.start_date);
    if (filters.end_date) params.append('end_date', filters.end_date);
    if (filters.limit !== undefined) params.append('limit', filters.limit.toString());
    if (filters.offset !== undefined) params.append('offset', filters.offset.toString());

    const queryString = params.toString();
    const endpoint = `/api/admin/traces${queryString ? `?${queryString}` : ''}`;

    try {
      return await this.request<TraceListResponse>(endpoint);
    } catch (error) {
      throw new Error(`Failed to fetch traces: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Get a single trace with full details and observations/spans
   */
  async getTrace(traceId: string): Promise<TraceDetail> {
    if (!traceId) {
      throw new Error('trace_id is required');
    }

    try {
      return await this.request<TraceDetail>(`/api/admin/traces/${traceId}`);
    } catch (error) {
      throw new Error(`Failed to fetch trace ${traceId}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Search traces by correlation_id or other query parameters
   */
  async searchTraces(query: string, filters: Omit<TraceFilter, 'trace_id'> = {}): Promise<TraceListResponse> {
    if (!query) {
      throw new Error('query parameter is required');
    }

    const params = new URLSearchParams();
    params.append('q', query);

    if (filters.user_id) params.append('user_id', filters.user_id);
    if (filters.session_id) params.append('session_id', filters.session_id);
    if (filters.name) params.append('name', filters.name);
    if (filters.status) params.append('status', filters.status);
    if (filters.start_date) params.append('start_date', filters.start_date);
    if (filters.end_date) params.append('end_date', filters.end_date);
    if (filters.limit !== undefined) params.append('limit', filters.limit.toString());
    if (filters.offset !== undefined) params.append('offset', filters.offset.toString());

    const queryString = params.toString();
    const endpoint = `/api/admin/traces/search?${queryString}`;

    try {
      return await this.request<TraceListResponse>(endpoint);
    } catch (error) {
      throw new Error(`Failed to search traces: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Get test results with optional filters and pagination
   */
  async getTestResults(filters: TestResultFilter = {}): Promise<TestResultsResponse> {
    const params = new URLSearchParams();

    if (filters.scenario_name) params.append('scenario_name', filters.scenario_name);
    if (filters.status) params.append('status', filters.status);
    if (filters.limit !== undefined) params.append('limit', filters.limit.toString());
    if (filters.offset !== undefined) params.append('offset', filters.offset.toString());

    const queryString = params.toString();
    const endpoint = `/api/admin/test-results${queryString ? `?${queryString}` : ''}`;

    try {
      return await this.request<TestResultsResponse>(endpoint);
    } catch (error) {
      throw new Error(`Failed to fetch test results: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Get a single test result
   */
  async getTestResult(testId: string | number): Promise<TestResult> {
    if (!testId) {
      throw new Error('test_id is required');
    }

    try {
      return await this.request<TestResult>(`/api/admin/test-results/${testId}`);
    } catch (error) {
      throw new Error(`Failed to fetch test result ${testId}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
}

// ==================== Export ====================

export const tracesApi = new TracesApiClient();
