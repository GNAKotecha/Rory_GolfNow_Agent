/**
 * Structured message schema for agent responses.
 * The agent returns JSON, frontend owns presentation.
 */

// Base action type for interactive elements
export interface MessageAction {
  label: string;
  href?: string;
  payload?: unknown;
  variant?: 'primary' | 'secondary' | 'danger';
}

// Form field definition
export interface FormField {
  id: string;
  label: string;
  type: 'text' | 'number' | 'select' | 'checkbox' | 'textarea';
  required?: boolean;
  placeholder?: string;
  options?: { value: string; label: string }[];
  defaultValue?: string | number | boolean;
}

// Tool result for displaying tool execution outcomes
export interface ToolResult {
  name: string;
  success: boolean;
  summary?: string;
  details?: Record<string, unknown>;
  duration_ms?: number;
}

// Individual message block types
export type MessageBlock =
  | { kind: 'markdown'; content: string }
  | { kind: 'text'; content: string }
  | { kind: 'table'; title?: string; columns: string[]; rows: (string | number)[][] }
  | { kind: 'card'; title: string; body: string; actions?: MessageAction[] }
  | { kind: 'form'; title?: string; fields: FormField[]; submitLabel?: string }
  | { kind: 'action'; label: string; payload: unknown }
  | { kind: 'actions'; actions: MessageAction[] }
  | { kind: 'code'; language?: string; content: string }
  | { kind: 'tool_result'; result: ToolResult }
  | { kind: 'tool_results'; results: ToolResult[] }
  | { kind: 'error'; title?: string; message: string }
  | { kind: 'info'; title?: string; message: string }
  | { kind: 'warning'; title?: string; message: string }
  | { kind: 'success'; title?: string; message: string }
  | { kind: 'timeline'; events: { time: string; title: string; description?: string }[] }
  | { kind: 'list'; title?: string; items: string[]; ordered?: boolean };

// Structured agent message - can contain multiple blocks
export interface StructuredMessage {
  blocks: MessageBlock[];
}

/**
 * Parse raw message content into structured blocks.
 * Tries to detect JSON structure, falls back to markdown.
 */
export function parseMessageContent(content: string): StructuredMessage {
  // First, try to parse as JSON structured message
  const trimmed = content.trim();
  
  // Check if it looks like JSON
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      const parsed = JSON.parse(trimmed);
      
      // Handle array of blocks directly
      if (Array.isArray(parsed)) {
        const validBlocks = parsed.filter(isValidBlock);
        if (validBlocks.length > 0) {
          return { blocks: validBlocks };
        }
      }
      
      // Handle single block object
      if (isValidBlock(parsed)) {
        return { blocks: [parsed] };
      }
      
      // Handle structured message format
      if (parsed.blocks && Array.isArray(parsed.blocks)) {
        const validBlocks = parsed.blocks.filter(isValidBlock);
        if (validBlocks.length > 0) {
          return { blocks: validBlocks };
        }
      }
      
      // Handle legacy answer format
      if (parsed.type === 'answer' && (parsed.title || parsed.body)) {
        const blocks: MessageBlock[] = [];
        if (parsed.body) {
          blocks.push({ kind: 'markdown', content: parsed.body });
        }
        if (parsed.actions && Array.isArray(parsed.actions)) {
          blocks.push({ kind: 'actions', actions: parsed.actions });
        }
        return { blocks };
      }
    } catch {
      // Not valid JSON, fall through to markdown
    }
  }
  
  // Default: treat as markdown
  return {
    blocks: [{ kind: 'markdown', content: content }]
  };
}

/**
 * Type guard to check if an object is a valid message block.
 */
function isValidBlock(obj: unknown): obj is MessageBlock {
  if (!obj || typeof obj !== 'object') return false;
  const block = obj as Record<string, unknown>;
  
  const validKinds = [
    'markdown', 'text', 'table', 'card', 'form', 'action', 'actions',
    'code', 'tool_result', 'tool_results', 'error', 'info', 'warning',
    'success', 'timeline', 'list'
  ];
  
  return typeof block.kind === 'string' && validKinds.includes(block.kind);
}

/**
 * Sanitize markdown content to prevent XSS.
 * Removes dangerous patterns while preserving formatting.
 */
export function sanitizeMarkdown(content: string): string {
  // Remove script tags and event handlers
  let sanitized = content
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/on\w+\s*=\s*["'][^"']*["']/gi, '')
    .replace(/javascript:/gi, '')
    .replace(/data:/gi, 'data-blocked:');
  
  return sanitized;
}
