'use client';

import { useState, useEffect, useRef, useMemo } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { apiClient, Session, Message } from '@/lib/api';
import { ChatWebSocket, StreamEvent } from '@/lib/websocket';
import { MessageRenderer } from '@/components/MessageRenderer';
import { parseMessageContent } from '@/lib/message-types';
import { NewSessionModal } from '@/components/NewSessionModal';
import { SkillSuggestions } from '@/components/SkillSuggestions';
import { useSkillInvocation } from '@/hooks/useSkillInvocation';

export default function ChatPage() {
  const { user, loading: authLoading, logout } = useAuth();
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [useStreaming, setUseStreaming] = useState(false); // Disabled until WebSocket is fixed (BUG-001)
  const [streamingStatus, setStreamingStatus] = useState<string>('');
  const [pendingAskUser, setPendingAskUser] = useState<StreamEvent | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editedTitle, setEditedTitle] = useState('');
  const [showNewSessionModal, setShowNewSessionModal] = useState(false);
  const [creatingSession, setCreatingSession] = useState(false);
  const [isAbortingRunId, setIsAbortingRunId] = useState<string | null>(null);
  const [showSkillSuggestions, setShowSkillSuggestions] = useState(false);
  const [selectedSkillIndex, setSelectedSkillIndex] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<ChatWebSocket | null>(null);
  const currentSessionIdRef = useRef<number>(0);
  const titleInputRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Skill invocation hook
  const { skills, fetchSkills, invokeSkill } = useSkillInvocation();

  // Fixed model - always use Haiku 4.5
  const selectedModel = 'auto';

  useEffect(() => {
    currentSessionIdRef.current = currentSession?.id || 0;
  }, [currentSession?.id]);

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

        ws.on('*', (event: StreamEvent) => {
          console.log('Stream event:', event);

          if (event.type === 'workflow_start') {
            setActiveRunId(event.run_id || null);
            setStreamingStatus('Processing...');
          } else if (event.type === 'step') {
            const toolList = event.tool_names?.join(', ') || `${event.tool_count} tools`;
            setStreamingStatus(`Step ${event.step_number}: ${toolList}`);
          } else if (event.type === 'tool_executing') {
            setStreamingStatus(`Running ${event.tool_name}...`);
          } else if (event.type === 'tool_call') {
            setStreamingStatus(`Calling ${event.tool_name}...`);
          } else if (event.type === 'tool_result') {
            const status = event.success ? '✓' : '✗';
            setStreamingStatus(`${status} ${event.tool_name}`);
          } else if (event.type === 'tool_error') {
            setStreamingStatus(`Error: ${event.tool_name}`);
          } else if (event.type === 'workflow_complete') {
            setStreamingStatus('');
            setPendingAskUser(null);
          } else if (event.type === 'ask_user') {
            setPendingAskUser(event);
            setActiveRunId(prev => event.run_id || prev);
            const prompt = event.message || 'I need more details...';
            setStreamingStatus(prompt);
            setLoading(false);
          } else if (event.type === 'final_response') {
            setActiveRunId(prev => event.run_id || prev);
            if (event.stopped_reason !== 'ask_user') {
              setPendingAskUser(null);
            }
            setStreamingStatus('');

            // Only add message if not an error
            if (event.stopped_reason !== 'error' && event.message) {
              const assistantMessage: Message = {
                id: Date.now(),
                session_id: currentSessionIdRef.current,
                role: 'assistant',
                content: event.message,
                created_at: new Date().toISOString(),
              };
              setMessages(prev => [...prev, assistantMessage]);
            } else if (event.stopped_reason === 'error') {
              // Show error message in status
              setStreamingStatus(`Error: ${event.message || 'Workflow failed'}`);
            }
            setLoading(false);
          } else if (event.type === 'error') {
            setStreamingStatus(`Error: ${event.error}`);
            setPendingAskUser(null);
            setLoading(false);
          }
        });
      })
      .catch((error) => {
        console.error('WebSocket connection failed:', error);
        setUseStreaming(false);
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

  useEffect(() => {
    if (isEditingTitle && titleInputRef.current) {
      titleInputRef.current.focus();
      titleInputRef.current.select();
    }
  }, [isEditingTitle]);

  // Fetch skills on mount
  useEffect(() => {
    if (user) {
      fetchSkills();
    }
  }, [user, fetchSkills]);

  async function loadSessions() {
    try {
      const data = await apiClient.getSessions();
      setSessions(data);
    } catch (error) {
      console.error('Failed to load sessions:', error);
    }
  }

  const loadMessages = async (sessionId: number) => {
    try {
      const data = await apiClient.getSessionMessages(sessionId);
      setMessages(data);
    } catch (error) {
      console.error('Failed to load messages:', error);
    }
  };

  const handleNewChat = () => {
    setShowNewSessionModal(true);
  };

  const handleCreateSession = async (title: string) => {
    setCreatingSession(true);
    try {
      const newSession = await apiClient.createSession(title);
      setSessions([newSession, ...sessions]);
      setCurrentSession(newSession);
      setMessages([]);
      setShowNewSessionModal(false);
    } catch (error) {
      console.error('Failed to create session:', error);
    } finally {
      setCreatingSession(false);
    }
  };

  const handleAbortRun = async () => {
    if (!currentSession?.id || !activeRunId) return;

    setIsAbortingRunId(activeRunId);
    try {
      await apiClient.abortSession(currentSession.id, activeRunId);
      wsRef.current?.disconnect();
      setLoading(false);
      setStreamingStatus('');
      setActiveRunId(null);
    } catch (error) {
      console.error('Failed to abort run:', error);
    } finally {
      setIsAbortingRunId(null);
    }
  };

  const handleSelectSession = async (session: Session) => {
    setCurrentSession(session);
    await loadMessages(session.id);
  };

  const handleTitleClick = () => {
    if (currentSession) {
      setEditedTitle(currentSession.title);
      setIsEditingTitle(true);
    }
  };

  const handleTitleSave = async () => {
    if (!currentSession || !editedTitle.trim()) {
      setIsEditingTitle(false);
      return;
    }

    try {
      const updatedSession = await apiClient.updateSession(currentSession.id, editedTitle.trim());
      setCurrentSession(updatedSession);
      setSessions(sessions.map(s => s.id === updatedSession.id ? updatedSession : s));
      setIsEditingTitle(false);
    } catch (error) {
      console.error('Failed to update session title:', error);
      setIsEditingTitle(false);
    }
  };

  const handleTitleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleTitleSave();
    } else if (e.key === 'Escape') {
      setIsEditingTitle(false);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setInput(value);

    // Show skill suggestions if input starts with "/"
    if (value.startsWith('/') && value.length > 1) {
      setShowSkillSuggestions(true);
      setSelectedSkillIndex(0);
    } else {
      setShowSkillSuggestions(false);
    }
  };

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showSkillSuggestions) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedSkillIndex(prev => (prev + 1) % skills.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedSkillIndex(prev => (prev === 0 ? skills.length - 1 : prev - 1));
    } else if (e.key === 'Enter' && skills.length > 0) {
      e.preventDefault();
      handleSkillSelect(skills[selectedSkillIndex]);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setShowSkillSuggestions(false);
    }
  };

  const handleSkillSelect = async (skill: { skill_name: string; description?: string | null }) => {
    setShowSkillSuggestions(false);
    setInput(`/${skill.skill_name} `);
    inputRef.current?.focus();

    // Auto-invoke the skill
    if (currentSession?.id) {
      setLoading(true);
      try {
        const result = await invokeSkill(skill.skill_name, {
          session_id: currentSession.id,
          user_id: user?.id,
        });

        // Add skill result to chat
        const skillMessage: Message = {
          id: Date.now(),
          session_id: currentSession.id,
          role: 'assistant',
          content: result.message,
          created_at: new Date().toISOString(),
        };
        setMessages(prev => [...prev, skillMessage]);
        setInput('');
      } catch (error) {
        console.error('Failed to invoke skill:', error);
        alert('Failed to invoke skill. Please try again.');
      } finally {
        setLoading(false);
      }
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');

    // Auto-create session if needed
    let sessionId = currentSession?.id;
    if (!sessionId) {
      try {
        setCreatingSession(true);
        const titlePreview = userMessage.substring(0, 50);
        const newSession = await apiClient.createSession(titlePreview);
        setSessions([newSession, ...sessions]);
        setCurrentSession(newSession);
        sessionId = newSession.id;
      } catch (error) {
        console.error('Failed to create session:', error);
        alert('Failed to create session');
        setInput(userMessage);
        return;
      } finally {
        setCreatingSession(false);
      }
    }

    setLoading(true);

    const optimisticUserMessage: Message = {
      id: Date.now(),
      session_id: sessionId,
      role: 'user',
      content: userMessage,
      created_at: new Date().toISOString(),
    };
    setMessages([...messages, optimisticUserMessage]);

    try {
      if (useStreaming && wsRef.current?.isConnected()) {
        if (pendingAskUser?.resume_token) {
          setStreamingStatus('Resuming...');
          wsRef.current.sendUserResponse(
            sessionId,
            {
              resume_token: pendingAskUser.resume_token,
              selected_option_id: pendingAskUser.options?.[0]?.id,
              input_values: {},
              freeform_text: userMessage,
            },
            pendingAskUser.run_id || activeRunId || undefined,
            undefined,
            selectedModel,
            false,
            undefined,
          );
        } else {
          setStreamingStatus('Sending...');
          wsRef.current.sendMessage(
            sessionId,
            userMessage,
            undefined,
            selectedModel,
            false,
            undefined,
          );
        }
      } else {
        if (pendingAskUser) {
          setMessages(prev => prev.filter(m => m.id !== optimisticUserMessage.id));
          alert('Please enable streaming for this workflow.');
          setLoading(false);
          return;
        }
        const response = await apiClient.sendMessage({
          session_id: sessionId,
          message: userMessage,
          model: selectedModel,
          allow_opus: false,
        });

        if (!currentSession) {
          const newSession = sessions.find(s => s.id === response.session_id);
          if (newSession) {
            setCurrentSession(newSession);
          } else {
            await loadSessions();
          }
        }

        // Refetch all messages from server to ensure UI is in sync (BUG-001 fix)
        await loadMessages(response.session_id);
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

  const isAwaitingResumeInput = Boolean(pendingAskUser?.resume_token);

  return (
    <div className="flex h-screen bg-white">
      {/* Sidebar */}
      <div
        className={`${
          sidebarOpen ? 'w-64' : 'w-0'
        } bg-gray-50 border-r border-gray-200 transition-all duration-300 overflow-hidden flex flex-col`}
      >
        <div className="p-3 border-b border-gray-200">
          <button
            onClick={handleNewChat}
            className="w-full bg-gray-900 hover:bg-gray-800 text-white text-sm font-medium py-2.5 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto py-2">
          {sessions.map((session) => (
            <button
              key={session.id}
              onClick={() => handleSelectSession(session)}
              className={`w-full text-left px-3 py-2.5 text-sm transition-colors truncate ${
                currentSession?.id === session.id
                  ? 'bg-gray-200 text-gray-900'
                  : 'text-gray-700 hover:bg-gray-100'
              }`}
            >
              {session.title}
            </button>
          ))}
        </div>

        {/* User info */}
        <div className="p-3 border-t border-gray-200">
          <div className="flex items-center justify-between">
            <div className="text-sm">
              <div className="font-medium text-gray-900">{user.name}</div>
              <div className="text-xs text-gray-500">{user.role}</div>
            </div>
            <button
              onClick={logout}
              className="text-gray-400 hover:text-gray-600 transition-colors p-1.5 rounded hover:bg-gray-100"
              title="Logout"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="bg-white border-b border-gray-200 px-4 py-3 flex items-center">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="mr-3 text-gray-500 hover:text-gray-700 transition-colors p-1.5 rounded hover:bg-gray-100"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          
          {isEditingTitle ? (
            <input
              ref={titleInputRef}
              type="text"
              value={editedTitle}
              onChange={(e) => setEditedTitle(e.target.value)}
              onBlur={handleTitleSave}
              onKeyDown={handleTitleKeyDown}
              className="text-lg font-medium text-gray-900 bg-transparent border-b-2 border-gray-400 focus:border-gray-900 outline-none px-1"
            />
          ) : (
            <h1 
              onClick={handleTitleClick}
              className="text-lg font-medium text-gray-900 cursor-pointer hover:text-gray-600 transition-colors"
              title="Click to rename"
            >
              {currentSession ? currentSession.title : 'New Chat'}
            </h1>
          )}

          <div className="ml-auto flex items-center gap-3">
            <span className="text-xs text-gray-400">Haiku 4.5</span>
            {useStreaming && (
              <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full font-medium">
                Live
              </span>
            )}
            {user?.role === 'admin' && (
              <div className="flex items-center gap-2 border-l border-gray-200 pl-3 ml-3">
                <a
                  href="/admin/skills"
                  className="px-2 py-1 text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded transition-colors"
                  title="Manage Skills"
                >
                  Skills
                </a>
                <a
                  href="/admin/mcp-connections"
                  className="px-2 py-1 text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded transition-colors"
                  title="Configure MCP Connections"
                >
                  MCPs
                </a>
                <a
                  href="/admin/workflows"
                  className="px-2 py-1 text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded transition-colors"
                  title="Manage Workflows"
                >
                  Workflows
                </a>
                <a
                  href="/admin/traces"
                  className="px-2 py-1 text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded transition-colors"
                  title="Trace Explorer"
                >
                  Traces
                </a>
              </div>
            )}
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto py-6 px-4 space-y-6">
            {messages.length === 0 && !loading && (
              <div className="text-center py-20">
                <h2 className="text-2xl font-semibold text-gray-900 mb-2">How can I help you today?</h2>
                <p className="text-gray-500">Ask me anything about BRS teesheet management.</p>
              </div>
            )}

            {messages.map((message) => (
              <div key={message.id} className="flex gap-4">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                  message.role === 'user' ? 'bg-gray-900 text-white' : 'bg-green-600 text-white'
                }`}>
                  {message.role === 'user' ? (
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 2a2 2 0 012 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 017 7h1a1 1 0 011 1v3a1 1 0 01-1 1h-1v1a2 2 0 01-2 2H5a2 2 0 01-2-2v-1H2a1 1 0 01-1-1v-3a1 1 0 011-1h1a7 7 0 017-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 012-2zM7.5 13a1.5 1.5 0 100 3 1.5 1.5 0 000-3zm9 0a1.5 1.5 0 100 3 1.5 1.5 0 000-3zM12 9a5 5 0 00-5 5v1h10v-1a5 5 0 00-5-5z"/>
                    </svg>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-900 mb-1">
                    {message.role === 'user' ? 'You' : 'Assistant'}
                  </div>
                  <div className="text-gray-700 leading-relaxed">
                    {message.role === 'user' ? (
                      <p className="whitespace-pre-wrap">{message.content}</p>
                    ) : (
                      <MessageRenderer message={parseMessageContent(message.content)} />
                    )}
                  </div>
                </div>
              </div>
            ))}

            {/* Status indicator */}
            {streamingStatus && (
              <div className="flex gap-4">
                <div className="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center flex-shrink-0">
                  <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                </div>
                <div className="flex-1">
                  <div className="text-sm font-medium text-gray-900 mb-1">Assistant</div>
                  <div className="text-gray-500 italic">{streamingStatus}</div>
                </div>
              </div>
            )}

            {/* Loading dots (HTTP mode) */}
            {loading && !useStreaming && !streamingStatus && (
              <div className="flex gap-4">
                <div className="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center flex-shrink-0">
                  <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                </div>
                <div className="flex-1">
                  <div className="text-sm font-medium text-gray-900 mb-1">Assistant</div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input */}
        <div className="border-t border-gray-200 bg-white p-4">
          <div className="max-w-3xl mx-auto relative">
            {isAwaitingResumeInput && (
              <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                <div className="font-medium">{pendingAskUser?.title || 'Additional information needed'}</div>
                {pendingAskUser?.reason && (
                  <div className="mt-1 text-xs text-amber-600">{pendingAskUser.reason}</div>
                )}
              </div>
            )}

            {/* Skill Suggestions Dropdown */}
            {showSkillSuggestions && (
              <SkillSuggestions
                skills={skills}
                selectedIndex={selectedSkillIndex}
                onSelect={handleSkillSelect}
                onClose={() => setShowSkillSuggestions(false)}
              />
            )}

            <form onSubmit={loading ? (e) => { e.preventDefault(); handleAbortRun(); } : handleSendMessage} className="flex gap-3">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleInputKeyDown}
                placeholder={isAwaitingResumeInput ? 'Provide details to continue...' : 'Message Assistant... (type / for skills)'}
                className="flex-1 bg-gray-100 text-gray-900 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-gray-400 placeholder-gray-500"
                disabled={loading && !isAwaitingResumeInput}
              />
              <button
                type="submit"
                disabled={(!loading && !input.trim())}
                className={`text-white font-medium px-5 py-3 rounded-xl transition-colors ${
                  loading
                    ? 'bg-red-600 hover:bg-red-700'
                    : 'bg-gray-900 hover:bg-gray-800 disabled:bg-gray-300 disabled:cursor-not-allowed'
                }`}
              >
                {loading ? (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/>
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                )}
              </button>
            </form>
          </div>
        </div>
      </div>

      <NewSessionModal
        isOpen={showNewSessionModal}
        onClose={() => setShowNewSessionModal(false)}
        onCreate={handleCreateSession}
        loading={creatingSession}
      />
    </div>
  );
}
