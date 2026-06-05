'use client';

import { useState, useEffect, useRef } from 'react';

interface NewSessionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (title: string) => Promise<void>;
  loading: boolean;
  autoTitle?: string;
}

export function NewSessionModal({ isOpen, onClose, onCreate, loading, autoTitle }: NewSessionModalProps) {
  const [title, setTitle] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (autoTitle) {
      setTitle(autoTitle);
    }
  }, [autoTitle]);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const sessionTitle = title.trim() || `Chat - ${new Date().toLocaleTimeString()}`;
    await onCreate(sessionTitle);
    setTitle('');
  };

  const handleClose = () => {
    setTitle('');
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-lg max-w-md w-full mx-4">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">New Conversation</h2>
          <p className="text-sm text-gray-600 mt-1">Give this chat a title (optional)</p>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-4">
          <input
            ref={inputRef}
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g., Golf course research"
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            disabled={loading}
          />
          <p className="text-xs text-gray-500 mt-2">
            Leave blank for auto-generated title
          </p>

          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={handleClose}
              disabled={loading}
              className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? 'Creating...' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
