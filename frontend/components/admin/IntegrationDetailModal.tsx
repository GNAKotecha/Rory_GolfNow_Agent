'use client';

import { useState } from 'react';
import { TenantMCPIntegration, HealthCheckResponse } from '@/lib/api';

interface IntegrationDetailModalProps {
  integration: TenantMCPIntegration | null;
  healthStatus: HealthCheckResponse | null;
  onClose: () => void;
  onDelete: () => void;
  onTestHealth: () => void;
  isLoading: boolean;
}

export default function IntegrationDetailModal({
  integration,
  healthStatus,
  onClose,
  onDelete,
  onTestHealth,
  isLoading,
}: IntegrationDetailModalProps) {
  const [activeTab, setActiveTab] = useState<'details' | 'credentials' | 'health'>('details');

  if (!integration) return null;

  const getHealthColor = (status: string | undefined): string => {
    switch (status) {
      case 'healthy':
        return 'text-green-600 bg-green-50';
      case 'unhealthy':
        return 'text-red-600 bg-red-50';
      case 'unknown':
        return 'text-yellow-600 bg-yellow-50';
      default:
        return 'text-gray-600 bg-gray-50';
    }
  };

  const formatAuthType = (authType: string): string => {
    const mapping: Record<string, string> = {
      oauth: 'OAuth',
      api_key: 'API Key',
      pat: 'Personal Access Token',
    };
    return mapping[authType] || authType;
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-gray-900">
            {integration.integration_name}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            <span className="sr-only">Close</span>
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200">
          <div className="flex">
            <button
              onClick={() => setActiveTab('details')}
              className={`px-6 py-3 font-medium text-sm border-b-2 ${
                activeTab === 'details'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`}
            >
              Details
            </button>
            <button
              onClick={() => setActiveTab('credentials')}
              className={`px-6 py-3 font-medium text-sm border-b-2 ${
                activeTab === 'credentials'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`}
            >
              Credentials
            </button>
            <button
              onClick={() => setActiveTab('health')}
              className={`px-6 py-3 font-medium text-sm border-b-2 ${
                activeTab === 'health'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`}
            >
              Health
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6">
          {activeTab === 'details' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Name</label>
                <p className="mt-1 text-sm text-gray-900">{integration.integration_name}</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Auth Type</label>
                <p className="mt-1 text-sm text-gray-900">{formatAuthType(integration.auth_type)}</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Status</label>
                <p className="mt-1">
                  <span
                    className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${
                      integration.is_enabled
                        ? 'bg-green-100 text-green-800'
                        : 'bg-red-100 text-red-800'
                    }`}
                  >
                    {integration.is_enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Created</label>
                <p className="mt-1 text-sm text-gray-900">
                  {new Date(integration.created_at).toLocaleString('en-US', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Last Updated</label>
                <p className="mt-1 text-sm text-gray-900">
                  {new Date(integration.updated_at).toLocaleString('en-US', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              </div>
            </div>
          )}

          {activeTab === 'credentials' && (
            <div className="space-y-4">
              <div className="bg-blue-50 border border-blue-200 rounded-md p-4">
                <p className="text-sm text-blue-800">
                  Credentials are stored securely and are not displayed here for security reasons. Use the "Test" button to verify the connection.
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Auth Type</label>
                <p className="mt-1 text-sm text-gray-900">{formatAuthType(integration.auth_type)}</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Status</label>
                <p className="mt-1">
                  <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                    Configured
                  </span>
                </p>
              </div>
            </div>
          )}

          {activeTab === 'health' && (
            <div className="space-y-4">
              {healthStatus ? (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Status</label>
                    <p className="mt-1">
                      <span
                        className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${getHealthColor(healthStatus.status)}`}
                      >
                        {healthStatus.status === 'healthy'
                          ? 'Healthy'
                          : healthStatus.status === 'unhealthy'
                          ? 'Unhealthy'
                          : 'Unknown'}
                      </span>
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Message</label>
                    <p className="mt-1 text-sm text-gray-900">{healthStatus.message}</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Checked At</label>
                    <p className="mt-1 text-sm text-gray-900">
                      {new Date(healthStatus.timestamp).toLocaleString('en-US', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </p>
                  </div>
                </>
              ) : (
                <div className="bg-gray-50 border border-gray-200 rounded-md p-4 text-center">
                  <p className="text-sm text-gray-600">Health check not performed yet</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 bg-gray-50 px-6 py-4 flex items-center justify-between">
          <button
            onClick={onTestHealth}
            disabled={isLoading}
            className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? 'Testing...' : 'Test Health'}
          </button>
          <div className="flex gap-3">
            <button
              onClick={onDelete}
              disabled={isLoading}
              className="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Delete
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-200 text-gray-800 text-sm font-medium rounded-md hover:bg-gray-300 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
