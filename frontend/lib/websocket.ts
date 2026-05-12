/**
 * WebSocket client for streaming chat responses.
 * Handles connection, authentication, and event streaming from the backend.
 */

export interface StreamEvent {
  type:
    | 'authenticated'
    | 'workflow_start'
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
    | 'workflow_complete'
    | 'approval_request'
    | 'ask_user'
    | 'final_response'
    | 'error';
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
  [key: string]: any;
}

export type StreamEventHandler = (event: StreamEvent) => void;

export class ChatWebSocket {
  private ws: WebSocket | null = null;
  private eventHandlers: Map<string, Set<StreamEventHandler>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000; // Start with 1 second

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
            resolve();
          } else if (data.type === 'error') {
            console.error('WebSocket error:', data.error);
            reject(new Error(data.error));
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

  sendMessage(sessionId: number, message: string, requireApproval?: boolean) {
    this.send({
      type: 'message',
      session_id: sessionId,
      message: message,
      require_approval: requireApproval,
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
    this.eventHandlers.clear();
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}
