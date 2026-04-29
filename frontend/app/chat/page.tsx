'use client';

import { useState, useEffect, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { apiClient, Session, Message } from '@/lib/api';
import { ChatWebSocket, StreamEvent } from '@/lib/websocket';

export default function ChatPage() {
  const { user, loading: authLoading, logout } = useAuth();
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [useStreaming, setUseStreaming] = useState(true); // NEW: Toggle for WebSocket
  const [streamingStatus, setStreamingStatus] = useState<string>(''); // NEW: Show streaming events
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<ChatWebSocket | null>(null);

  // Initialize WebSocket
  useEffect(() => {
    if (!user || !useStreaming) return;

    const token = localStorage.getItem('access_token');
    if (!token) return;

    const ws = new ChatWebSocket(process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000');

    ws.connect(token)
      .then(() => {
        console.log('WebSocket connected and authenticated');
        wsRef.current = ws;

        // Listen to all events
        ws.on('*', (event: StreamEvent) => {
          console.log('Stream event:', event);

          if (event.type === 'workflow_start') {
            setStreamingStatus(`Starting workflow (${event.available_tools} tools available)...`);
          } else if (event.type === 'step') {
            setStreamingStatus(`Step ${event.step_number}: ${event.action}...`);
          } else if (event.type === 'tool_call') {
            setStreamingStatus(`Calling tool: ${event.tool_name}...`);
          } else if (event.type === 'tool_result') {
            setStreamingStatus(`Tool ${event.tool_name} completed`);
          } else if (event.type === 'plan_created') {
            setStreamingStatus(`Created plan with ${event.steps?.length || 0} steps`);
          } else if (event.type === 'plan_progress') {
            setStreamingStatus(`Progress: ${Math.round(event.progress * 100)}%`);
          } else if (event.type === 'final_response') {
            setStreamingStatus('');
            // Add assistant message
            const assistantMessage: Message = {
              id: Date.now(),
              session_id: currentSession?.id || 0,
              role: 'assistant',
              content: event.message,
              created_at: new Date().toISOString(),
            };
            setMessages(prev => [...prev, assistantMessage]);
            setLoading(false);
          } else if (event.type === 'error') {
            setStreamingStatus(`Error: ${event.error}`);
            setLoading(false);
          }
        });
      })
      .catch((error) => {
        console.error('WebSocket connection failed:', error);
        setUseStreaming(false); // Fallback to HTTP
      });

    return () => {
      ws.disconnect();
    };
  }, [user, useStreaming]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.push('/login');
      return;
    }
    loadSessions();
  }, [user, authLoading, router]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadSessions = async () => {
    try {
      const data = await apiClient.getSessions();
      setSessions(data);
    } catch (error) {
      console.error('Failed to load sessions:', error);
    }
  };

  const loadMessages = async (sessionId: number) => {
    try {
      const data = await apiClient.getSessionMessages(sessionId);
      setMessages(data);
    } catch (error) {
      console.error('Failed to load messages:', error);
    }
  };

  const handleNewChat = async () => {
    try {
      const newSession = await apiClient.createSession();
      setSessions([newSession, ...sessions]);
      setCurrentSession(newSession);
      setMessages([]);
    } catch (error) {
      console.error('Failed to create session:', error);
    }
  };

  const handleSelectSession = async (session: Session) => {
    setCurrentSession(session);
    await loadMessages(session.id);
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    setLoading(true);

    // Optimistically add user message
    const optimisticUserMessage: Message = {
      id: Date.now(),
      session_id: currentSession?.id || 0,
      role: 'user',
      content: userMessage,
      created_at: new Date().toISOString(),
    };
    setMessages([...messages, optimisticUserMessage]);

    try {
      if (useStreaming && wsRef.current?.isConnected()) {
        // Use WebSocket for streaming
        setStreamingStatus('Sending message...');
        wsRef.current.sendMessage(
          currentSession?.id || 0,
          userMessage
        );
      } else {
        // Fallback to HTTP
        const response = await apiClient.sendMessage({
          session_id: currentSession?.id,
          message: userMessage,
        });

        if (!currentSession) {
          const newSession = sessions.find(s => s.id === response.session_id);
          if (newSession) {
            setCurrentSession(newSession);
          } else {
            await loadSessions();
          }
        }

        setMessages(prev => {
          const withoutOptimistic = prev.filter(m => m.id !== optimisticUserMessage.id);
          return [...withoutOptimistic, response.message, response.response].filter(Boolean);
        });
        setLoading(false);
      }
    } catch (error) {
      console.error('Failed to send message:', error);
      setMessages(prev => prev.filter(m => m.id !== optimisticUserMessage.id));
      alert('Failed to send message. Please try again.');
      setLoading(false);
    }
  };

  if (!user) {
    return null;
  }

  return (
    <div className="flex h-screen bg-gray-900 text-white">
      {/* Sidebar */}
      <div
        className={`${
          sidebarOpen ? 'w-64' : 'w-0'
        } bg-gray-800 transition-all duration-300 overflow-hidden flex flex-col`}
      >
        <div className="p-4 border-b border-gray-700">
          <button
            onClick={handleNewChat}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-lg transition-colors"
          >
            + New Chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* Streaming Toggle */}
          <div className="p-4 border-b border-gray-700">
            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={useStreaming}
                onChange={(e) => setUseStreaming(e.target.checked)}
                className="form-checkbox h-4 w-4 text-blue-600"
              />
              <span className="text-sm text-gray-300">Enable Streaming</span>
            </label>
          </div>

          {/* Recent Conversations */}
          <div className="p-4">
            <div className="text-xs text-gray-500 uppercase font-semibold mb-2">Recents</div>
            <div className="space-y-1">
              {sessions.map((session) => (
                <button
                  key={session.id}
                  onClick={() => handleSelectSession(session)}
                  className={`w-full text-left px-4 py-2 rounded-lg transition-colors truncate ${
                    currentSession?.id === session.id
                      ? 'bg-gray-700 text-white'
                      : 'text-gray-300 hover:bg-gray-700'
                  }`}
                >
                  {session.title}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* User info and logout */}
        <div className="p-4 border-t border-gray-700">
          <div className="flex items-center justify-between">
            <div className="text-sm">
              <div className="font-medium">{user.name}</div>
              <div className="text-xs text-gray-400">{user.role}</div>
            </div>
            <button
              onClick={logout}
              className="text-gray-400 hover:text-white transition-colors"
              title="Logout"
            >
              🚪
            </button>
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="bg-gray-800 border-b border-gray-700 p-4 flex items-center">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="mr-4 text-gray-400 hover:text-white transition-colors"
          >
            ☰
          </button>
          <h1 className="text-xl font-semibold">
            {currentSession ? currentSession.title : 'New Chat'}
          </h1>
          {useStreaming && (
            <span className="ml-4 px-2 py-1 bg-green-600 text-xs rounded">
              STREAMING
            </span>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${
                message.role === 'user' ? 'justify-end' : 'justify-start'
              }`}
            >
              <div
                className={`max-w-3xl px-4 py-2 rounded-lg ${
                  message.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-700 text-gray-100'
                }`}
              >
                <div className="whitespace-pre-wrap">{message.content}</div>
              </div>
            </div>
          ))}

          {/* Streaming Status */}
          {streamingStatus && (
            <div className="flex justify-start">
              <div className="max-w-3xl px-4 py-2 rounded-lg bg-gray-700 text-gray-300 italic">
                {streamingStatus}
              </div>
            </div>
          )}

          {/* Loading indicator (for HTTP mode) */}
          {loading && !useStreaming && (
            <div className="flex justify-start">
              <div className="max-w-3xl px-4 py-2 rounded-lg bg-gray-700 text-gray-100">
                <div className="flex items-center space-x-2">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-gray-700 p-4">
          <form onSubmit={handleSendMessage} className="flex space-x-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your message..."
              className="flex-1 bg-gray-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-600"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white font-medium px-6 py-2 rounded-lg transition-colors"
            >
              Send
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
