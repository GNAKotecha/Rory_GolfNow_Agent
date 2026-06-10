'use client';

import { useState } from 'react';
import { TenantMCPIntegration, apiClient, HealthCheckResponse } from '@/lib/api';
import { getStatusColors } from '@/lib/statusColors';

interface TestConnectionModalProps {
  isOpen: boolean;
  connection: TenantMCPIntegration | null;
  onClose: () => void;
  loading: boolean;
}

export default function TestConnectionModal({
  isOpen,
  connection,
  onClose,
  loading: parentLoading,
}: TestConnectionModalProps) {
  const [testStatus, setTestStatus] = useState<HealthCheckResponse | null>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);
  const [hasTestedConnection, setHasTestedConnection] = useState(false);

  if (!isOpen || !connection) return null;

  const handleTestConnection = async () => {
    setTestLoading(true);
    setTestError(null);
    setTestStatus(null);

    try {
      const result = await apiClient.testConnection(connection.id);
      setTestStatus(result);
      setHasTestedConnection(true);
    } catch (err) {
      setTestError(err instanceof Error ? err.message : 'Failed to test connection');
      setHasTestedConnection(true);
    } finally {
      setTestLoading(false);
    }
  };

  const handleClose = () => {
    setTestStatus(null);
    setTestError(null);
    setHasTestedConnection(false);
    onClose();
  };


  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-lg max-w-md w-full mx-4">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Test Connection</h2>
          <p className="text-sm text-gray-600 mt-1">{connection.integration_name}</p>
        </div>

        {/* Body */}
        <div className="px-6 py-4">
          {!hasTestedConnection ? (
            <div className="text-center py-8">
              <p className="text-sm text-gray-600 mb-4">
                Test the connectivity and authentication of this MCP connection
              </p>
              <button
                onClick={handleTestConnection}
                disabled={testLoading || parentLoading}
                className="w-full px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {testLoading ? 'Testing...' : 'Run Test'}
              </button>
            </div>
          ) : testError ? (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-md">
              <h3 className="text-sm font-semibold text-red-800 mb-1">Test Failed</h3>
              <p className="text-sm text-red-700">{testError}</p>
            </div>
          ) : testStatus ? (
            <>
              {(() => {
                const { textColor, bgColor } = getStatusColors(testStatus.status);
                return (
                  <>
                    <div className={`mb-4 p-4 border rounded-md ${bgColor}`}>
                      <div className="flex items-center justify-between">
                        <h3 className={`text-sm font-semibold ${textColor}`}>
                          {testStatus.status === 'healthy' ? 'Connection Healthy' : 'Connection Issue'}
                        </h3>
                        <span
                          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            testStatus.status === 'healthy'
                              ? 'bg-green-100 text-green-800'
                              : 'bg-red-100 text-red-800'
                          }`}
                        >
                          {testStatus.status.charAt(0).toUpperCase() + testStatus.status.slice(1)}
                        </span>
                      </div>
                      <p className="text-sm text-gray-600 mt-2">{testStatus.message}</p>
                      <p className="text-xs text-gray-500 mt-2">
                        Tested: {new Date(testStatus.timestamp.endsWith('Z') || testStatus.timestamp.includes('+') ? testStatus.timestamp : testStatus.timestamp + 'Z').toLocaleString()}
                      </p>
                    </div>

                    <button
                      onClick={handleTestConnection}
                      disabled={testLoading || parentLoading}
                      className="w-full px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 rounded-md hover:bg-blue-100 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {testLoading ? 'Testing...' : 'Test Again'}
                    </button>
                  </>
                );
              })()}
            </>
          ) : null}

          {/* Additional Info */}
          <div className="mt-6 p-3 bg-gray-50 rounded-md">
            <h4 className="text-xs font-semibold text-gray-700 mb-2">Connection Details</h4>
            <dl className="space-y-2">
              <div className="flex justify-between">
                <dt className="text-xs text-gray-600">Name:</dt>
                <dd className="text-xs font-medium text-gray-900">
                  {connection.integration_name}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-xs text-gray-600">Auth Type:</dt>
                <dd className="text-xs font-medium text-gray-900">
                  {connection.auth_type === 'api_key' ? 'API Key' : connection.auth_type.toUpperCase()}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-xs text-gray-600">Status:</dt>
                <dd
                  className={`text-xs font-medium ${
                    connection.is_enabled ? 'text-green-600' : 'text-gray-600'
                  }`}
                >
                  {connection.is_enabled ? 'Enabled' : 'Disabled'}
                </dd>
              </div>
            </dl>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200">
          <button
            onClick={handleClose}
            className="w-full px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
