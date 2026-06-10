'use client';

import { useState, useEffect } from 'react';
import { TenantMCPIntegration, TenantMCPIntegrationCreate, TenantMCPIntegrationUpdate } from '@/lib/api';
import { getMCPFormDefaults } from '@/lib/formDefaults';

interface AddMCPModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (data: TenantMCPIntegrationCreate) => Promise<void>;
  onUpdate?: (id: number, data: TenantMCPIntegrationUpdate) => Promise<void>;
  editIntegration?: TenantMCPIntegration | null;
  loading: boolean;
}

const AUTH_TYPES = [
  { value: 'oauth', label: 'OAuth 2.0' },
  { value: 'api_key', label: 'API Key' },
  { value: 'pat', label: 'Personal Access Token' },
];

export default function AddMCPModal({
  isOpen,
  onClose,
  onAdd,
  onUpdate,
  editIntegration,
  loading,
}: AddMCPModalProps) {
  const isEditMode = !!editIntegration;
  const [formData, setFormData] = useState(getMCPFormDefaults());
  const [error, setError] = useState<string | null>(null);

  // Populate form when editing
  useEffect(() => {
    if (editIntegration) {
      setFormData({
        integration_name: editIntegration.integration_name,
        auth_type: editIntegration.auth_type as 'oauth' | 'api_key' | 'pat',
        config: { ...editIntegration.config, credentials: '' },
      });
    } else {
      setFormData(getMCPFormDefaults());
    }
    setError(null);
  }, [editIntegration, isOpen]);

  if (!isOpen) return null;

  const credentialLabel = {
    api_key: 'API Key',
    pat: 'Personal Access Token',
    oauth: 'OAuth Credentials',
  }[formData.auth_type] ?? 'Credentials';

  const credentialPlaceholder = {
    oauth: 'client_id:client_secret (optional for some MCPs)',
    api_key: 'Your API key',
    pat: 'Your personal access token',
  }[formData.auth_type] ?? '';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!formData.integration_name.trim()) {
      setError('Connection name is required');
      return;
    }
    if (!formData.config?.server_url?.trim()) {
      setError('Server URL is required');
      return;
    }

    try {
      if (isEditMode && onUpdate && editIntegration) {
        const updatePayload: TenantMCPIntegrationUpdate = {
          integration_name: formData.integration_name,
          config: { ...formData.config },
        };
        // Only include credentials if the user typed something new
        if (!formData.config?.credentials?.trim()) {
          delete updatePayload.config!.credentials;
        }
        await onUpdate(editIntegration.id, updatePayload);
      } else {
        await onAdd({
          integration_name: formData.integration_name,
          auth_type: formData.auth_type,
          config: formData.config,
        });
      }
      setFormData(getMCPFormDefaults());
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${isEditMode ? 'update' : 'add'} connection`);
    }
  };

  const handleClose = () => {
    setFormData(getMCPFormDefaults());
    setError(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-lg max-w-md w-full mx-4">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEditMode ? 'Edit MCP Connection' : 'Add MCP Connection'}
          </h2>
          <p className="text-sm text-gray-600 mt-1">
            {isEditMode
              ? 'Update the configuration for this MCP server'
              : 'Configure a new external MCP server connection'}
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="px-6 py-4">
          {/* Error */}
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
              value={formData.integration_name}
              onChange={(e) => setFormData({ ...formData, integration_name: e.target.value })}
              placeholder="e.g., github-api"
              className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              disabled={loading}
            />
            <p className="text-xs text-gray-500 mt-1">Unique identifier for this MCP connection</p>
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
              placeholder="http://localhost:3000 or https://api.example.com"
              className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              disabled={loading}
            />
            <p className="text-xs text-gray-500 mt-1">Full URL to the MCP server endpoint</p>
          </div>

          {/* Auth Type — read-only in edit mode */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-900">Authentication Type</label>
            <select
              value={formData.auth_type}
              onChange={(e) =>
                setFormData({ ...formData, auth_type: e.target.value as 'oauth' | 'api_key' | 'pat' })
              }
              className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-50"
              disabled={loading || isEditMode}
            >
              {AUTH_TYPES.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
            <p className="text-xs text-gray-500 mt-1">
              {isEditMode ? 'Auth type cannot be changed after creation' : 'Select how to authenticate with the MCP server'}
            </p>
          </div>

          {/* Credentials — always optional */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-900">
              {credentialLabel}
              <span className="ml-1 text-xs font-normal text-gray-400">(optional)</span>
            </label>
            <input
              type="password"
              value={formData.config?.credentials || ''}
              onChange={(e) =>
                setFormData({ ...formData, config: { ...formData.config, credentials: e.target.value } })
              }
              placeholder={isEditMode ? 'Leave blank to keep existing credentials' : credentialPlaceholder}
              className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              disabled={loading}
            />
            <p className="text-xs text-gray-500 mt-1">
              {isEditMode
                ? 'Credentials are encrypted and stored securely. Leave blank to keep current value.'
                : 'Credentials are encrypted and stored securely. Not required for all MCP types.'}
            </p>
          </div>

          {/* Buttons */}
          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={handleClose}
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
              {loading
                ? isEditMode ? 'Saving...' : 'Adding...'
                : isEditMode ? 'Save Changes' : 'Add Connection'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
