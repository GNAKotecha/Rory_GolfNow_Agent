'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  MessageBlock,
  StructuredMessage,
  MessageAction,
  ToolResult,
  FormField,
  sanitizeMarkdown,
} from '@/lib/message-types';

/**
 * Main renderer for structured messages.
 */
export function MessageRenderer({ message }: { message: StructuredMessage }) {
  return (
    <div className="space-y-3">
      {message.blocks.map((block, index) => (
        <BlockRenderer key={index} block={block} />
      ))}
    </div>
  );
}

/**
 * Render individual message blocks.
 */
function BlockRenderer({ block }: { block: MessageBlock }) {
  switch (block.kind) {
    case 'markdown':
      return <MarkdownBlock content={block.content} />;
    case 'text':
      return <TextBlock content={block.content} />;
    case 'table':
      return <TableBlock title={block.title} columns={block.columns} rows={block.rows} />;
    case 'card':
      return <CardBlock title={block.title} body={block.body} actions={block.actions} />;
    case 'code':
      return <CodeBlock language={block.language} content={block.content} />;
    case 'actions':
      return <ActionsBlock actions={block.actions} />;
    case 'action':
      return <ActionsBlock actions={[{ label: block.label, payload: block.payload }]} />;
    case 'tool_result':
      return <ToolResultBlock result={block.result} />;
    case 'tool_results':
      return <ToolResultsBlock results={block.results} />;
    case 'error':
      return <AlertBlock variant="error" title={block.title} message={block.message} />;
    case 'warning':
      return <AlertBlock variant="warning" title={block.title} message={block.message} />;
    case 'info':
      return <AlertBlock variant="info" title={block.title} message={block.message} />;
    case 'success':
      return <AlertBlock variant="success" title={block.title} message={block.message} />;
    case 'list':
      return <ListBlock title={block.title} items={block.items} ordered={block.ordered} />;
    case 'timeline':
      return <TimelineBlock events={block.events} />;
    case 'form':
      return <FormBlock title={block.title} fields={block.fields} submitLabel={block.submitLabel} />;
    default:
      return <TextBlock content={JSON.stringify(block)} />;
  }
}

/**
 * Markdown renderer with sanitization and styling.
 */
function MarkdownBlock({ content }: { content: string }) {
  const sanitized = sanitizeMarkdown(content);
  
  return (
    <div className="prose prose-gray prose-sm max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Style links
          a: ({ href, children }) => (
            <a 
              href={href} 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-blue-600 hover:text-blue-800 underline"
            >
              {children}
            </a>
          ),
          // Style code blocks
          code: ({ className, children, ...props }) => {
            const isInline = !className;
            if (isInline) {
              return (
                <code className="bg-gray-100 text-gray-800 px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          // Style code blocks (pre)
          pre: ({ children }) => (
            <pre className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto text-sm">
              {children}
            </pre>
          ),
          // Style lists
          ul: ({ children }) => (
            <ul className="list-disc list-inside space-y-1 text-gray-700">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside space-y-1 text-gray-700">
              {children}
            </ol>
          ),
          // Style headings
          h1: ({ children }) => (
            <h1 className="text-xl font-semibold text-gray-900 mt-4 mb-2">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-lg font-semibold text-gray-900 mt-3 mb-2">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-base font-semibold text-gray-900 mt-2 mb-1">{children}</h3>
          ),
          // Style paragraphs
          p: ({ children }) => (
            <p className="text-gray-700 leading-relaxed">{children}</p>
          ),
          // Style blockquotes
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-gray-300 pl-4 italic text-gray-600">
              {children}
            </blockquote>
          ),
          // Style tables
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th className="px-3 py-2 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-2 text-gray-700 border-t border-gray-100">
              {children}
            </td>
          ),
        }}
      >
        {sanitized}
      </ReactMarkdown>
    </div>
  );
}

/**
 * Plain text block.
 */
function TextBlock({ content }: { content: string }) {
  return <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{content}</p>;
}

/**
 * Data table block.
 */
function TableBlock({ 
  title, 
  columns, 
  rows 
}: { 
  title?: string; 
  columns: string[]; 
  rows: (string | number)[][] 
}) {
  return (
    <div className="overflow-x-auto">
      {title && <h4 className="text-sm font-medium text-gray-900 mb-2">{title}</h4>}
      <table className="min-w-full divide-y divide-gray-200 text-sm border border-gray-200 rounded-lg overflow-hidden">
        <thead className="bg-gray-50">
          <tr>
            {columns.map((col, i) => (
              <th 
                key={i} 
                className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-100">
          {rows.map((row, i) => (
            <tr key={i} className="hover:bg-gray-50">
              {row.map((cell, j) => (
                <td key={j} className="px-4 py-2 text-gray-700">
                  {String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Card block with optional actions.
 */
function CardBlock({ 
  title, 
  body, 
  actions 
}: { 
  title: string; 
  body: string; 
  actions?: MessageAction[] 
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
      <h4 className="text-base font-medium text-gray-900 mb-2">{title}</h4>
      <p className="text-gray-700 text-sm mb-3">{body}</p>
      {actions && actions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {actions.map((action, i) => (
            <ActionButton key={i} action={action} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Code block with syntax highlighting placeholder.
 */
function CodeBlock({ language, content }: { language?: string; content: string }) {
  return (
    <div className="relative">
      {language && (
        <div className="absolute top-2 right-2 text-xs text-gray-400 font-mono">
          {language}
        </div>
      )}
      <pre className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto text-sm font-mono">
        <code>{content}</code>
      </pre>
    </div>
  );
}

/**
 * Action buttons block.
 */
function ActionsBlock({ actions }: { actions: MessageAction[] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {actions.map((action, i) => (
        <ActionButton key={i} action={action} />
      ))}
    </div>
  );
}

/**
 * Single action button.
 */
function ActionButton({ action }: { action: MessageAction }) {
  const baseStyles = "px-3 py-1.5 text-sm font-medium rounded-lg transition-colors";
  const variantStyles = {
    primary: "bg-gray-900 text-white hover:bg-gray-800",
    secondary: "bg-gray-100 text-gray-700 hover:bg-gray-200 border border-gray-300",
    danger: "bg-red-600 text-white hover:bg-red-700",
  };
  
  const styles = `${baseStyles} ${variantStyles[action.variant || 'secondary']}`;
  
  if (action.href) {
    return (
      <a href={action.href} className={styles} target="_blank" rel="noopener noreferrer">
        {action.label}
      </a>
    );
  }
  
  return (
    <button className={styles} onClick={() => console.log('Action:', action.payload)}>
      {action.label}
    </button>
  );
}

/**
 * Tool result display.
 */
function ToolResultBlock({ result }: { result: ToolResult }) {
  return (
    <div className={`border rounded-lg p-3 text-sm ${
      result.success 
        ? 'bg-green-50 border-green-200' 
        : 'bg-red-50 border-red-200'
    }`}>
      <div className="flex items-center gap-2 mb-1">
        <span className={result.success ? 'text-green-600' : 'text-red-600'}>
          {result.success ? '✓' : '✗'}
        </span>
        <span className="font-medium text-gray-900">{result.name}</span>
        {result.duration_ms && (
          <span className="text-xs text-gray-500">({result.duration_ms}ms)</span>
        )}
      </div>
      {result.summary && (
        <p className="text-gray-700 ml-5">{result.summary}</p>
      )}
    </div>
  );
}

/**
 * Multiple tool results.
 */
function ToolResultsBlock({ results }: { results: ToolResult[] }) {
  return (
    <div className="space-y-2">
      {results.map((result, i) => (
        <ToolResultBlock key={i} result={result} />
      ))}
    </div>
  );
}

/**
 * Alert/notification blocks.
 */
function AlertBlock({ 
  variant, 
  title, 
  message 
}: { 
  variant: 'error' | 'warning' | 'info' | 'success';
  title?: string;
  message: string;
}) {
  const styles = {
    error: 'bg-red-50 border-red-200 text-red-800',
    warning: 'bg-amber-50 border-amber-200 text-amber-800',
    info: 'bg-blue-50 border-blue-200 text-blue-800',
    success: 'bg-green-50 border-green-200 text-green-800',
  };
  
  const icons = {
    error: '✗',
    warning: '⚠',
    info: 'ℹ',
    success: '✓',
  };
  
  return (
    <div className={`border rounded-lg p-3 text-sm ${styles[variant]}`}>
      <div className="flex items-start gap-2">
        <span className="text-lg leading-none">{icons[variant]}</span>
        <div>
          {title && <div className="font-medium mb-1">{title}</div>}
          <p>{message}</p>
        </div>
      </div>
    </div>
  );
}

/**
 * List block.
 */
function ListBlock({ 
  title, 
  items, 
  ordered 
}: { 
  title?: string; 
  items: string[]; 
  ordered?: boolean 
}) {
  const ListTag = ordered ? 'ol' : 'ul';
  const listStyle = ordered ? 'list-decimal' : 'list-disc';
  
  return (
    <div>
      {title && <h4 className="text-sm font-medium text-gray-900 mb-2">{title}</h4>}
      <ListTag className={`${listStyle} list-inside space-y-1 text-gray-700 text-sm`}>
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ListTag>
    </div>
  );
}

/**
 * Timeline block.
 */
function TimelineBlock({ 
  events 
}: { 
  events: { time: string; title: string; description?: string }[] 
}) {
  return (
    <div className="space-y-3">
      {events.map((event, i) => (
        <div key={i} className="flex gap-3">
          <div className="flex flex-col items-center">
            <div className="w-2 h-2 bg-gray-400 rounded-full"></div>
            {i < events.length - 1 && <div className="w-0.5 flex-1 bg-gray-200"></div>}
          </div>
          <div className="pb-3">
            <div className="text-xs text-gray-500">{event.time}</div>
            <div className="font-medium text-gray-900 text-sm">{event.title}</div>
            {event.description && (
              <div className="text-gray-600 text-sm">{event.description}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Form block (display only for now).
 */
function FormBlock({ 
  title, 
  fields, 
  submitLabel 
}: { 
  title?: string; 
  fields: FormField[]; 
  submitLabel?: string 
}) {
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
      {title && <h4 className="text-sm font-medium text-gray-900 mb-3">{title}</h4>}
      <div className="space-y-3">
        {fields.map((field) => (
          <div key={field.id}>
            <label className="block text-sm text-gray-700 mb-1">
              {field.label}
              {field.required && <span className="text-red-500 ml-1">*</span>}
            </label>
            {field.type === 'textarea' ? (
              <textarea 
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
                placeholder={field.placeholder}
                rows={3}
              />
            ) : field.type === 'select' ? (
              <select className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-gray-400">
                {field.options?.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            ) : field.type === 'checkbox' ? (
              <input type="checkbox" className="h-4 w-4 text-gray-900 rounded" />
            ) : (
              <input 
                type={field.type}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
                placeholder={field.placeholder}
              />
            )}
          </div>
        ))}
      </div>
      <button className="mt-4 px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800">
        {submitLabel || 'Submit'}
      </button>
    </div>
  );
}
