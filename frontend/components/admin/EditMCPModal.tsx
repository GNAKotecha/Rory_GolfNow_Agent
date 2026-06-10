'use client';

import { useState, useEffect } from 'react';
import { TenantMCPIntegration, TenantMCPIntegrationUpdate } from '@/lib/api';

interface EditMCPModalProps {
  isOpen: boolean;
  integration: TenantMCPIntegration | null;
  onClose: () => void;
  onSave: (id: number, data: TenantMCPIntegrationUpdate) => Promise<void>;
  loading: boolean;
}

const AUTH_TYPES = [
  { value: 'oauth', label: 'OAuth 2.0' },
  { value: 'api_key', label: 'API Key' },
  { value: 'pat', label: 'Personal Access Token' },
];

export default function EditMCPModal({ isOpen, integration, onClose, onSave, loading }: EditMCPModalProps) {
  const [formData, setFormData] = useState<TenantMCPIntegrationUpdate>({});
  const [credentials, setCredentials] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (integration) {
      setFormData({
        integration_name: integration.integration_name,
        config: { ...integration.config },
      });
      setCredentials('');
      setError(null);
    }
  }, [integration]);

  if (!isOpen || !integration) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!formData.integration_name?.trim()) {
      setError('Connection name is required');
      return;
    }
    if (!formData.config?.server_url?.trim()) {
      setError('Server URL is required');
      return;
    }

    const updatePayload: TenantMCPIntegrationUpdate = {
      integration_name: formData.integration_name,
      config: { ...formData.config },
    };

    // Only include credentials if the user entered a new value
    if (credentials.trim()) {
      updatePayload.config = {
        ...updatePayload.config,
        credentials,
      };
    }

    try {
      await onSave(integration.id, updatePayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save changes');
    }
  };

  const authType = integration.auth_type;
  const credentialLabel =
    authType === 'api_key' ? 'API Key' :
    authType === 'oauth' ? 'OAuth Client ID:Secret' :
    'Personal Access Token';

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-lg max-w-md w-full mx-4">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Edit MCP Connection</h2>
          <p className="text-sm text-gray-600 mt-1">
            Update settings for <span className="font-medium">{integration.integration_name}</span>
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="px-6 py-4">
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          {/* Connection Name */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-900">Connection Name</label>
            <input
              type="text"
              value={formData.integration_name || ''}
              onChange={(e) => setFormData({ ...formData, integration_name: e.target.value })}
              className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              disabled={loading}
            />
          </div>

          {/* Server URL */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-900">Server URL</label>
            <input
              type="url"
              value={formData.config?.server_url || ''}
              onChange={(e) =>
                setFormData({ ...formData, config: { ...formData.config, server_url: e.target.value } })
              }
              placeholder="https://api.example.com/mcp"
              className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              disabled={loading}
            />
          </div>

          {/* Auth type display (read-only — changing auth type requires delete + recreate) */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-900">Authentication Type</label>
            <input
              type="text"
              value={AUTH_TYPES.find((t) => t.value === authType)?.label ?? authType}
              readOnly
              className="mt-1 w-full px-3 py-2 border border-gray-200 rounded-md bg-gray-50 text-gray-500 cursor-not-allowed"
            />
            <p className="text-xs text-gray-500 mt-1">To change auth type, delete and re-add the connection.</p>
          </div>

          {/* New credentials (optional) */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-900">
              {credentialLabel} <span className="font-normal text-gray-500">(leave blank to keep existing)</span>
            </label>
            <input
              type="password"
              value={credentials}
              onChange={(e) => setCredentials(e.target.value)}
              placeholder={
                authType === 'oauth' ? 'client_id:client_secret' :
                authType === 'api_key' ? 'Your API key' :
                'Your personal access token'
              }
              className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              disabled={loading}
            />
            <p className="text-xs text-gray-500 mt-1">Credentials are encrypted and stored securely.</p>
          </div>

          {/* Buttons */}
          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
