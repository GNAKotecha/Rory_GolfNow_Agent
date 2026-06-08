'use client';

import { useState, useEffect } from 'react';
import { apiClient, TenantMCPIntegration, TenantMCPIntegrationCreate, HealthCheckResponse } from '@/lib/api';
import IntegrationFiltersPanel from '@/components/admin/IntegrationFiltersPanel';
import IntegrationListTable from '@/components/admin/IntegrationListTable';
import IntegrationDetailModal from '@/components/admin/IntegrationDetailModal';
import IntegrationCreateModal from '@/components/admin/IntegrationCreateModal';
import CredentialSetupModal from '@/components/admin/CredentialSetupModal';

const DEFAULT_LIMIT = 10;

export default function IntegrationsPage() {
  // Data state
  const [integrations, setIntegrations] = useState<TenantMCPIntegration[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Filters
  const [filters, setFilters] = useState({
    search: '',
    auth_type: 'all' as 'oauth' | 'api_key' | 'pat' | 'all',
    enabled: 'all' as 'all' | 'true' | 'false',
  });

  // Pagination
  const [itemsPerPage, setItemsPerPage] = useState(DEFAULT_LIMIT);
  const [currentPage, setCurrentPage] = useState(1);

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showCredentialModal, setShowCredentialModal] = useState(false);
  const [selectedIntegration, setSelectedIntegration] = useState<TenantMCPIntegration | null>(null);
  const [selectedAuthType, setSelectedAuthType] = useState<'oauth' | 'api_key' | 'pat'>('api_key');
  const [healthStatus, setHealthStatus] = useState<Record<number, HealthCheckResponse | null>>({});

  // Operation states
  const [operationLoading, setOperationLoading] = useState(false);
  const [selectedHealthId, setSelectedHealthId] = useState<number | null>(null);

  // Fetch integrations on mount and when filters change
  useEffect(() => {
    fetchIntegrations();
  }, [filters, itemsPerPage]);

  // Clear success message after 3 seconds
  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [successMessage]);

  const fetchIntegrations = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.getIntegrations();

      // Apply filters
      let filtered = response.filter((integration) => {
        // Search filter
        if (filters.search && !integration.integration_name.toLowerCase().includes(filters.search.toLowerCase())) {
          return false;
        }

        // Auth type filter
        if (filters.auth_type !== 'all' && integration.auth_type !== filters.auth_type) {
          return false;
        }

        // Enabled filter
        if (filters.enabled !== 'all') {
          const isEnabled = filters.enabled === 'true';
          if (integration.is_enabled !== isEnabled) {
            return false;
          }
        }

        return true;
      });

      setIntegrations(filtered);
      setCurrentPage(1); // Reset to first page on filter change
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch integrations');
      setIntegrations([]);
    } finally {
      setLoading(false);
    }
  };

  const handleFilterChange = (newFilters: any) => {
    setFilters(newFilters);
  };

  const handleClearFilters = () => {
    setFilters({
      search: '',
      auth_type: 'all',
      enabled: 'all',
    });
  };

  const handleCreateIntegration = async (data: TenantMCPIntegrationCreate) => {
    setOperationLoading(true);

    try {
      const newIntegration = await apiClient.createIntegration(data);
      setSelectedIntegration(newIntegration);
      setSelectedAuthType(data.auth_type as 'oauth' | 'api_key' | 'pat');
      setShowCreateModal(false);
      setShowCredentialModal(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create integration');
    } finally {
      setOperationLoading(false);
    }
  };

  const handleCredentialsSetup = async () => {
    setSuccessMessage('Integration created and credentials configured successfully');
    setShowCredentialModal(false);
    setSelectedIntegration(null);
    await fetchIntegrations();
  };

  const handleEditIntegration = (integration: TenantMCPIntegration) => {
    setSelectedIntegration(integration);
    setShowDetailModal(true);
    // Fetch health status if not already cached
    if (!(integration.id in healthStatus)) {
      fetchHealthStatus(integration.id);
    }
  };

  const handleDeleteIntegration = async () => {
    if (!selectedIntegration) return;

    if (!confirm(`Are you sure you want to delete "${selectedIntegration.integration_name}"?`)) {
      return;
    }

    setOperationLoading(true);

    try {
      await apiClient.deleteIntegration(selectedIntegration.id);
      setSuccessMessage('Integration deleted successfully');
      setShowDetailModal(false);
      setSelectedIntegration(null);
      await fetchIntegrations();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete integration');
    } finally {
      setOperationLoading(false);
    }
  };

  const handleToggleEnable = async (id: number, shouldEnable: boolean) => {
    setOperationLoading(true);

    try {
      if (shouldEnable) {
        await apiClient.enableIntegration(id);
        setSuccessMessage('Integration enabled');
      } else {
        await apiClient.disableIntegration(id);
        setSuccessMessage('Integration disabled');
      }
      await fetchIntegrations();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update integration');
    } finally {
      setOperationLoading(false);
    }
  };

  const handleTestIntegration = async (id: number) => {
    setOperationLoading(true);
    setSelectedHealthId(id);

    try {
      const result = await apiClient.checkIntegrationHealth(id);
      setHealthStatus((prev) => ({
        ...prev,
        [id]: result,
      }));
      setSuccessMessage(
        result.status === 'healthy'
          ? 'Integration is healthy'
          : `Health check completed: ${result.status}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to test integration');
    } finally {
      setOperationLoading(false);
      setSelectedHealthId(null);
    }
  };

  const fetchHealthStatus = async (integrationId: number) => {
    try {
      const result = await apiClient.checkIntegrationHealth(integrationId);
      setHealthStatus((prev) => ({
        ...prev,
        [integrationId]: result,
      }));
    } catch (err) {
      // Silently fail for background health checks
      console.error('Failed to fetch health status:', err);
    }
  };

  const handleStoreApiKey = async (integrationId: number, apiKey: string, baseUrl?: string) => {
    setOperationLoading(true);

    try {
      await apiClient.storeApiKey(integrationId, apiKey, baseUrl);
      setSuccessMessage('API Key stored successfully');
      await handleCredentialsSetup();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to store API key');
    } finally {
      setOperationLoading(false);
    }
  };

  const handleStorePAT = async (integrationId: number, token: string, baseUrl?: string) => {
    setOperationLoading(true);

    try {
      await apiClient.storePAT(integrationId, token, baseUrl);
      setSuccessMessage('Personal Access Token stored successfully');
      await handleCredentialsSetup();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to store PAT');
    } finally {
      setOperationLoading(false);
    }
  };

  const handleInitiateOAuth = async (integrationId: number) => {
    setOperationLoading(true);

    try {
      const result = await apiClient.initiateOAuth(integrationId);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to initiate OAuth');
      throw err;
    } finally {
      setOperationLoading(false);
    }
  };

  const handleCompleteOAuth = async (integrationId: number, code: string, state: string) => {
    setOperationLoading(true);

    try {
      await apiClient.completeOAuthCallback(integrationId, code, state);
      setSuccessMessage('OAuth flow completed successfully');
      await handleCredentialsSetup();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to complete OAuth');
    } finally {
      setOperationLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Integrations</h1>
          <p className="text-gray-600 mt-2">Manage MCP integrations and connect external services</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          disabled={loading || operationLoading}
          className="px-4 py-2 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          + New Integration
        </button>
      </div>

      {/* Messages */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <p className="text-sm text-red-800">{error}</p>
          <button
            onClick={() => setError(null)}
            className="text-xs text-red-600 hover:text-red-800 mt-2 underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {successMessage && (
        <div className="bg-green-50 border border-green-200 rounded-md p-4">
          <p className="text-sm text-green-800">{successMessage}</p>
        </div>
      )}

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Filters Sidebar */}
        <div className="lg:col-span-1">
          <IntegrationFiltersPanel
            filters={filters}
            onFilterChange={handleFilterChange}
            onClearFilters={handleClearFilters}
            loading={loading}
          />
        </div>

        {/* Integrations Table */}
        <div className="lg:col-span-3">
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-6">
            <IntegrationListTable
              integrations={integrations}
              healthStatus={healthStatus}
              onEdit={handleEditIntegration}
              onDelete={(integration) => {
                setSelectedIntegration(integration);
                handleDeleteIntegration();
              }}
              onTest={handleTestIntegration}
              onToggleEnable={handleToggleEnable}
              loading={loading || operationLoading || selectedHealthId !== null}
              itemsPerPage={itemsPerPage}
              currentPage={currentPage}
              onPageChange={setCurrentPage}
            />
          </div>
        </div>
      </div>

      {/* Modals */}
      {showCreateModal && (
        <IntegrationCreateModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={handleCreateIntegration}
          isLoading={operationLoading}
        />
      )}

      {showDetailModal && selectedIntegration && (
        <IntegrationDetailModal
          integration={selectedIntegration}
          healthStatus={healthStatus[selectedIntegration.id] || null}
          onClose={() => {
            setShowDetailModal(false);
            setSelectedIntegration(null);
          }}
          onDelete={handleDeleteIntegration}
          onTestHealth={() => handleTestIntegration(selectedIntegration.id)}
          isLoading={operationLoading || selectedHealthId === selectedIntegration.id}
        />
      )}

      {showCredentialModal && selectedIntegration && (
        <CredentialSetupModal
          integration={selectedIntegration}
          authType={selectedAuthType}
          onClose={() => {
            setShowCredentialModal(false);
            setSelectedIntegration(null);
          }}
          onSuccess={handleCredentialsSetup}
          onStoreApiKey={handleStoreApiKey}
          onStorePAT={handleStorePAT}
          onInitiateOAuth={handleInitiateOAuth}
          onCompleteOAuth={handleCompleteOAuth}
          onTestConnection={async (id) => {
            const result = await apiClient.testConnection(id);
            return result;
          }}
          isLoading={operationLoading}
        />
      )}
    </div>
  );
}
