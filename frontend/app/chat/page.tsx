'use client';

import { useState, useEffect, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { apiClient, Session, Message } from '@/lib/api';

export default function ChatPage() {
  const { user, loading: authLoading, logout } = useAuth();
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Wait for auth to finish loading
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
      id: Date.now(), // Temporary ID
      session_id: currentSession?.id || 0,
      role: 'user',
      content: userMessage,
      created_at: new Date().toISOString(),
    };
    setMessages([...messages, optimisticUserMessage]);

    try {
      const response = await apiClient.sendMessage({
        session_id: currentSession?.id,
        message: userMessage,
      });

      // Update current session if this was a new chat
      if (!currentSession) {
        const newSession = sessions.find(s => s.id === response.session_id);
        if (newSession) {
          setCurrentSession(newSession);
        } else {
          await loadSessions();
        }
      }

      // Replace optimistic message with real messages from server
      setMessages(prev => {
        // Remove the optimistic message
        const withoutOptimistic = prev.filter(m => m.id !== optimisticUserMessage.id);
        // Add real messages (user + assistant)
        return [...withoutOptimistic, response.message, response.response].filter(Boolean);
      });
    } catch (error) {
      console.error('Failed to send message:', error);
      // Remove optimistic message on error
      setMessages(prev => prev.filter(m => m.id !== optimisticUserMessage.id));
      alert('Failed to send message. Please try again.');
    } finally {
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
          {/* Navigation Items */}
          <div className="p-4 space-y-2">
            <button className="w-full text-left px-4 py-2 rounded-lg hover:bg-gray-700 transition-colors text-gray-300">
              🔍 Search
            </button>
            <button className="w-full text-left px-4 py-2 rounded-lg hover:bg-gray-700 transition-colors text-gray-400 cursor-not-allowed">
              📱 Apps <span className="text-xs">(Coming Soon)</span>
            </button>
            <button className="w-full text-left px-4 py-2 rounded-lg hover:bg-gray-700 transition-colors text-gray-400 cursor-not-allowed">
              ⚡ Skills <span className="text-xs">(Coming Soon)</span>
            </button>
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
            {currentSession ? currentSession.title : 'Rory - Your AI Assistant'}
          </h1>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && !currentSession && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <h2 className="text-3xl font-bold mb-2">Welcome to Rory</h2>
                <p className="text-gray-400">Start a new chat to get started</p>
              </div>
            </div>
          )}

          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-2xl px-4 py-2 rounded-lg ${
                  message.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-700 text-gray-100'
                }`}
              >
                {message.content}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="bg-gray-700 text-gray-100 px-4 py-2 rounded-lg">
                <div className="flex space-x-2">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200"></div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="bg-gray-800 border-t border-gray-700 p-4">
          <form onSubmit={handleSendMessage} className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Message Rory..."
              className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
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
