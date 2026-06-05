'use client';

import { useState, useEffect } from 'react';
import { TenantMCPIntegration } from '@/lib/api';

interface CredentialSetupModalProps {
  integration: TenantMCPIntegration | null;
  authType: 'oauth' | 'api_key' | 'pat';
  onClose: () => void;
  onSuccess: () => void;
  onStoreApiKey: (integrationId: number, apiKey: string, baseUrl?: string) => Promise<void>;
  onStorePAT: (integrationId: number, token: string, baseUrl?: string) => Promise<void>;
  onInitiateOAuth: (integrationId: number) => Promise<{ authorizationUrl: string; state: string }>;
  onCompleteOAuth: (integrationId: number, code: string, state: string) => Promise<void>;
  onTestConnection: (integrationId: number) => Promise<any>;
  isLoading: boolean;
}

export default function CredentialSetupModal({
  integration,
  authType,
  onClose,
  onSuccess,
  onStoreApiKey,
  onStorePAT,
  onInitiateOAuth,
  onCompleteOAuth,
  onTestConnection,
  isLoading,
}: CredentialSetupModalProps) {
  const [apiKey, setApiKey] = useState('');
  const [pat, setPat] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ status: string; message: string } | null>(null);
  const [oauthLoading, setOAuthLoading] = useState(false);

  // Clear error state when modal opens or closes
  useEffect(() => {
    setError(null);
  }, []);

  if (!integration) return null;

  const handleTestConnection = async () => {
    if (!apiKey && !pat) {
      setError('Please enter credentials first');
      return;
    }

    setTesting(true);
    setError(null);

    try {
      const result = await onTestConnection(integration.id);
      setTestResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connection test failed');
    } finally {
      setTesting(false);
    }
  };

  const handleStoreAndContinue = async () => {
    if (authType === 'api_key') {
      if (!apiKey.trim()) {
        setError('API Key is required');
        return;
      }
      try {
        await onStoreApiKey(integration.id, apiKey, baseUrl || undefined);
        onSuccess();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to store API key');
      }
    } else if (authType === 'pat') {
      if (!pat.trim()) {
        setError('Personal Access Token is required');
        return;
      }
      try {
        await onStorePAT(integration.id, pat, baseUrl || undefined);
        onSuccess();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to store PAT');
      }
    }
  };

  const handleInitiateOAuth = async () => {
    setOAuthLoading(true);
    setError(null);
    try {
      const result = await onInitiateOAuth(integration.id);
      // Open OAuth flow in new window
      const width = 500;
      const height = 600;
      const left = window.screenX + (window.outerWidth - width) / 2;
      const top = window.screenY + (window.outerHeight - height) / 2;

      const oauthWindow = window.open(
        result.authorizationUrl,
        'oauth_window',
        `width=${width},height=${height},left=${left},top=${top}`
      );

      if (!oauthWindow) {
        setError('Failed to open OAuth window. Please check browser popup settings.');
        setOAuthLoading(false);
        return;
      }

      // Poll for completion (in production, use postMessage)
      const pollInterval = setInterval(() => {
        try {
          if (oauthWindow.closed) {
            clearInterval(pollInterval);
            setOAuthLoading(false);
            // Assume success if window closed - in production, verify via backend
            onSuccess();
          }
        } catch (err) {
          clearInterval(pollInterval);
          setOAuthLoading(false);
        }
      }, 1000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to initiate OAuth flow');
      setOAuthLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50" role="dialog" aria-modal="true" aria-labelledby="credential-modal-title">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full">
        {/* Header */}
        <div className="border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <h2 id="credential-modal-title" className="text-xl font-semibold text-gray-900">Setup Credentials</h2>
          <button
            onClick={onClose}
            disabled={isLoading || testing}
            className="text-gray-400 hover:text-gray-600 disabled:opacity-50"
          >
            <span className="sr-only">Close</span>
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          <div>
            <h3 className="font-medium text-gray-900">Integration: {integration.integration_name}</h3>
            <p className="text-sm text-gray-600 mt-1">
              Setting up {authType === 'oauth' ? 'OAuth 2.0' : authType === 'api_key' ? 'API Key' : 'Personal Access Token'} authentication
            </p>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-md p-4">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          {testResult && (
            <div
              className={`border rounded-md p-4 ${
                testResult.status === 'healthy'
                  ? 'bg-green-50 border-green-200'
                  : 'bg-yellow-50 border-yellow-200'
              }`}
            >
              <p className={`text-sm ${testResult.status === 'healthy' ? 'text-green-800' : 'text-yellow-800'}`}>
                <strong>Test Result:</strong> {testResult.message}
              </p>
            </div>
          )}

          {authType === 'oauth' ? (
            // OAuth Flow
            <div className="bg-blue-50 border border-blue-200 rounded-md p-4 space-y-3">
              <p className="text-sm text-blue-900">
                Click the button below to authorize this integration using OAuth 2.0. You'll be redirected to the provider's login page.
              </p>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleInitiateOAuth}
                  disabled={isLoading || testing || oauthLoading}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
                >
                  {oauthLoading && (
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                  )}
                  {oauthLoading ? 'Authorizing...' : 'Start OAuth Authorization'}
                </button>
              </div>
            </div>
          ) : authType === 'api_key' ? (
            // API Key Flow
            <div className="space-y-4">
              <div>
                <label htmlFor="apiKey" className="block text-sm font-medium text-gray-700 mb-2">
                  API Key <span className="text-red-500">*</span>
                </label>
                <input
                  id="apiKey"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="Enter your API key"
                  disabled={isLoading || testing}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
                />
              </div>
              <div>
                <label htmlFor="baseUrl" className="block text-sm font-medium text-gray-700 mb-2">
                  Base URL (Optional)
                </label>
                <input
                  id="baseUrl"
                  type="url"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="https://api.example.com"
                  disabled={isLoading || testing}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
                />
              </div>
            </div>
          ) : (
            // PAT Flow
            <div className="space-y-4">
              <div>
                <label htmlFor="pat" className="block text-sm font-medium text-gray-700 mb-2">
                  Personal Access Token <span className="text-red-500">*</span>
                </label>
                <textarea
                  id="pat"
                  value={pat}
                  onChange={(e) => setPat(e.target.value)}
                  placeholder="Paste your personal access token here"
                  rows={4}
                  disabled={isLoading || testing}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
                />
              </div>
              <div>
                <label htmlFor="baseUrlPat" className="block text-sm font-medium text-gray-700 mb-2">
                  Base URL (Optional)
                </label>
                <input
                  id="baseUrlPat"
                  type="url"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="https://api.example.com"
                  disabled={isLoading || testing}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
                />
              </div>
            </div>
          )}

          {authType !== 'oauth' && (
            <button
              onClick={handleTestConnection}
              disabled={isLoading || testing || (!apiKey && !pat)}
              className="w-full px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {testing ? 'Testing...' : 'Test Connection'}
            </button>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 bg-gray-50 px-6 py-4 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            disabled={isLoading || testing}
            className="px-4 py-2 bg-white text-gray-700 text-sm font-medium rounded-md border border-gray-300 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Cancel
          </button>
          {authType !== 'oauth' && (
            <button
              onClick={handleStoreAndContinue}
              disabled={isLoading || testing || (!apiKey && !pat)}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? 'Saving...' : 'Save Credentials'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
