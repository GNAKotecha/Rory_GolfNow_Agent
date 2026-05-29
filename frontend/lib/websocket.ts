/**
 * WebSocket client for streaming chat responses.
 * Handles connection, authentication, and event streaming from the backend.
 * 
 * Task E1: Defines stable event contract for headless/CLI mode.
 * Task E2: Adds HITL (Human-in-the-loop) types for ask_user scenarios.
 */

/**
 * Event types for workflow streaming.
 * All events include run_id for multi-run correlation.
 */
export type StreamEventType =
  | 'authenticated'
  | 'workflow_start'
  | 'workflow_complete'
  | 'workflow_error'
  | 'step'
  | 'tool_executing'
  | 'tool_call'
  | 'tool_result'
  | 'tool_error'
  | 'plan_created'
  | 'plan_progress'
  | 'loop_detected'
  | 'low_confidence'
  | 'max_steps_reached'
  | 'approval_request'
  | 'ask_user'
  | 'user_response'
  | 'user_response_error'
  | 'final_response'
  | 'error';

/**
 * Reasons for human-in-the-loop intervention.
 */
export type AskUserReason =
  | 'auth_required'
  | 'validation_failed'
  | 'rbac_denied'
  | 'semantic_error'
  | 'transport_exhausted'
  | 'terminal_error'
  | 'user_input_needed'
  | 'approval_needed'
  | 'ambiguous_intent';

/**
 * Input field types for structured user prompts.
 */
export type InputFieldType = 'text' | 'password' | 'select' | 'multiselect' | 'confirm' | 'number' | 'file';

/**
 * A single input field for user prompts.
 */
export interface InputField {
  name: string;
  label: string;
  field_type: InputFieldType;
  required: boolean;
  default?: any;
  placeholder?: string;
  options?: Array<{ value: string; label: string }>;
  validation_pattern?: string;
  min_value?: number;
  max_value?: number;
}

/**
 * A selectable option for remediation.
 */
export interface RemediationOption {
  id: string;
  label: string;
  description?: string;
  action: 'continue' | 'retry' | 'skip' | 'abort';
  requires_input: boolean;
  input_fields?: InputField[];
}

/**
 * Structured payload for ask_user events (Task E2).
 */
export interface AskUserPayload {
  reason: AskUserReason;
  title: string;
  message: string;
  options: RemediationOption[];
  context: Record<string, any>;
  resume_token: string;
  timeout_seconds?: number;
  allow_freeform: boolean;
}

/**
 * Response envelope for user input (Task E2).
 */
export interface UserResponsePayload {
  resume_token: string;
  selected_option_id?: string;
  input_values?: Record<string, any>;
  freeform_text?: string;
}

/**
 * Base stream event interface with run_id correlation (Task E1).
 */
export interface StreamEvent {
  type: StreamEventType;
  // Task E1: All events include run_id for multi-run correlation
  run_id?: string;
  timestamp?: string;
  // Common fields
  step_number?: number;
  tool_name?: string;
  tool_names?: string[];
  tool_count?: number;
  max_steps?: number;
  success?: boolean;
  duration_ms?: number;
  error?: string;
  result_preview?: string;
  progress?: number;
  // Task E2: HITL fields
  reason?: AskUserReason;
  title?: string;
  message?: string;
  options?: RemediationOption[];
  context?: Record<string, any>;
  resume_token?: string;
  timeout_seconds?: number;
  allow_freeform?: boolean;
  // Allow additional fields
  [key: string]: any;
}

export type StreamEventHandler = (event: StreamEvent) => void;

export class ChatWebSocket {
  private ws: WebSocket | null = null;
  private eventHandlers: Map<string, Set<StreamEventHandler>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000; // Start with 1 second
  private authenticated = false;

  constructor(private wsUrl: string) {}

  connect(token: string): Promise<void> {
    return new Promise((resolve, reject) => {
      // Convert http/https URL to ws/wss
      const url = this.wsUrl.replace(/^http/, 'ws') + '/api/ws/chat';

      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.authenticated = false;

        // Send authentication message
        this.send({
          type: 'auth',
          token: token,
        });
      };

      this.ws.onmessage = (event) => {
        try {
          const data: StreamEvent = JSON.parse(event.data);

          if (data.type === 'authenticated') {
            console.log('WebSocket authenticated');
            this.authenticated = true;
            resolve();
          } else if (data.type === 'error') {
            if (!this.authenticated) {
              console.error('WebSocket error:', data.error);
              reject(new Error(data.error));
            } else {
              this.notifyHandlers(data);
            }
          } else {
            this.notifyHandlers(data);
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        reject(error);
      };

      this.ws.onclose = () => {
        console.log('WebSocket closed');
        this.attemptReconnect(token);
      };
    });
  }

  private attemptReconnect(token: string) {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

    setTimeout(() => {
      this.connect(token).catch(console.error);
    }, delay);
  }

  sendMessage(
    sessionId: number,
    message: string,
    requireApproval?: boolean,
    model?: string,
    allowOpus?: boolean,
    opusJustification?: string,
  ) {
    this.send({
      type: 'message',
      session_id: sessionId,
      message: message,
      require_approval: requireApproval,
      model: model,
      allow_opus: allowOpus,
      opus_justification: opusJustification,
    });
  }

  sendUserResponse(
    sessionId: number,
    payload: UserResponsePayload,
    runId?: string,
    requireApproval?: boolean,
    model?: string,
    allowOpus?: boolean,
    opusJustification?: string,
  ) {
    this.send({
      type: 'user_response',
      session_id: sessionId,
      run_id: runId,
      resume_token: payload.resume_token,
      selected_option_id: payload.selected_option_id,
      input_values: payload.input_values,
      freeform_text: payload.freeform_text,
      require_approval: requireApproval,
      model: model,
      allow_opus: allowOpus,
      opus_justification: opusJustification,
    });
  }

  on(eventType: string, handler: StreamEventHandler) {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, new Set());
    }
    this.eventHandlers.get(eventType)!.add(handler);
  }

  off(eventType: string, handler: StreamEventHandler) {
    const handlers = this.eventHandlers.get(eventType);
    if (handlers) {
      handlers.delete(handler);
    }
  }

  private notifyHandlers(event: StreamEvent) {
    // Notify specific event handlers
    const handlers = this.eventHandlers.get(event.type);
    if (handlers) {
      handlers.forEach(handler => handler(event));
    }

    // Notify wildcard handlers
    const wildcardHandlers = this.eventHandlers.get('*');
    if (wildcardHandlers) {
      wildcardHandlers.forEach(handler => handler(event));
    }
  }

  private send(data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    } else {
      console.error('WebSocket not connected');
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.authenticated = false;
    this.eventHandlers.clear();
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}
