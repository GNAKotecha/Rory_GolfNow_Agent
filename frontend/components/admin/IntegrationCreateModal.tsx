'use client';

import { useState } from 'react';
import { TenantMCPIntegrationCreate } from '@/lib/api';

interface IntegrationCreateModalProps {
  onClose: () => void;
  onSuccess: (data: TenantMCPIntegrationCreate) => void;
  isLoading: boolean;
}

export default function IntegrationCreateModal({
  onClose,
  onSuccess,
  isLoading,
}: IntegrationCreateModalProps) {
  const [name, setName] = useState('');
  const [authType, setAuthType] = useState<'oauth' | 'api_key' | 'pat'>('api_key');
  const [configJson, setConfigJson] = useState('{}');
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validation
    if (!name.trim()) {
      setError('Integration name is required');
      return;
    }

    if (name.trim().length < 3) {
      setError('Integration name must be at least 3 characters');
      return;
    }

    // Validate JSON
    let config: Record<string, any>;
    try {
      config = JSON.parse(configJson);
    } catch {
      setError('Invalid JSON in config field');
      return;
    }

    const data: TenantMCPIntegrationCreate = {
      integration_name: name.trim(),
      auth_type: authType,
      config,
    };

    onSuccess(data);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full">
        {/* Header */}
        <div className="border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-gray-900">Create Integration</h2>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="text-gray-400 hover:text-gray-600 disabled:opacity-50"
          >
            <span className="sr-only">Close</span>
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-md p-4">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          {/* Name */}
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
              Integration Name <span className="text-red-500">*</span>
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., GitHub Integration"
              disabled={isLoading}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>

          {/* Auth Type */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-3">
              Authentication Type <span className="text-red-500">*</span>
            </label>
            <div className="space-y-2">
              <label className="flex items-center">
                <input
                  type="radio"
                  name="authType"
                  value="oauth"
                  checked={authType === 'oauth'}
                  onChange={(e) => setAuthType(e.target.value as 'oauth')}
                  disabled={isLoading}
                  className="h-4 w-4 text-blue-600 border-gray-300 focus:ring-blue-500 disabled:opacity-50"
                />
                <span className="ml-3 text-sm text-gray-700">OAuth 2.0</span>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="authType"
                  value="api_key"
                  checked={authType === 'api_key'}
                  onChange={(e) => setAuthType(e.target.value as 'api_key')}
                  disabled={isLoading}
                  className="h-4 w-4 text-blue-600 border-gray-300 focus:ring-blue-500 disabled:opacity-50"
                />
                <span className="ml-3 text-sm text-gray-700">API Key</span>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="authType"
                  value="pat"
                  checked={authType === 'pat'}
                  onChange={(e) => setAuthType(e.target.value as 'pat')}
                  disabled={isLoading}
                  className="h-4 w-4 text-blue-600 border-gray-300 focus:ring-blue-500 disabled:opacity-50"
                />
                <span className="ml-3 text-sm text-gray-700">Personal Access Token (PAT)</span>
              </label>
            </div>
          </div>

          {/* Config JSON */}
          <div>
            <label htmlFor="config" className="block text-sm font-medium text-gray-700 mb-2">
              Configuration (JSON)
            </label>
            <textarea
              id="config"
              value={configJson}
              onChange={(e) => setConfigJson(e.target.value)}
              placeholder='{"key": "value"}'
              rows={6}
              disabled={isLoading}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <p className="mt-2 text-xs text-gray-500">
              Optional configuration in JSON format for the integration
            </p>
          </div>
        </form>

        {/* Footer */}
        <div className="border-t border-gray-200 bg-gray-50 px-6 py-4 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            disabled={isLoading}
            className="px-4 py-2 bg-white text-gray-700 text-sm font-medium rounded-md border border-gray-300 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? 'Creating...' : 'Next: Setup Credentials'}
          </button>
        </div>
      </div>
    </div>
  );
}
