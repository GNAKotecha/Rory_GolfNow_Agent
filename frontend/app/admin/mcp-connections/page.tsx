'use client';

import { useState, useEffect } from 'react';
import { apiClient, TenantMCPIntegration, TenantMCPIntegrationCreate } from '@/lib/api';
import MCPConnectionsList from '@/components/admin/MCPConnectionsList';
import AddMCPModal from '@/components/admin/AddMCPModal';
import TestConnectionModal from '@/components/admin/TestConnectionModal';
import DiscoverToolsModal from '@/components/admin/DiscoverToolsModal';
import DeleteConnectionConfirm from '@/components/admin/DeleteConnectionConfirm';

interface Filters {
  search: string;
  auth_type: 'oauth' | 'api_key' | 'pat' | 'all';
  enabled: 'all' | 'true' | 'false';
}

const DEFAULT_LIMIT = 20;

export default function MCPConnectionsPage() {
  // Data state
  const [connections, setConnections] = useState<TenantMCPIntegration[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modal states
  const [showAddModal, setShowAddModal] = useState(false);
  const [showTestModal, setShowTestModal] = useState(false);
  const [showDiscoverModal, setShowDiscoverModal] = useState(false);
  const [selectedConnection, setSelectedConnection] = useState<TenantMCPIntegration | null>(null);
  const [deleteConfirmConnection, setDeleteConfirmConnection] = useState<TenantMCPIntegration | null>(null);

  const [operationLoading, setOperationLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Filter state
  const [filters, setFilters] = useState<Filters>({
    search: '',
    auth_type: 'all',
    enabled: 'all',
  });

  // Fetch connections when page changes
  useEffect(() => {
    fetchConnections();
  }, [page]);

  // Clear success message after 3 seconds
  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [successMessage]);

  const fetchConnections = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.getIntegrations();
      // Paginate locally
      const offset = (page - 1) * DEFAULT_LIMIT;
      const limit = DEFAULT_LIMIT;
      const paginated = response.slice(offset, offset + limit);

      setConnections(paginated);
      setTotal(response.length);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to fetch MCP connections'
      );
      setConnections([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  const handleAddConnection = async (data: TenantMCPIntegrationCreate) => {
    setOperationLoading(true);
    try {
      await apiClient.createIntegration(data);
      setSuccessMessage('MCP connection added successfully');
      setShowAddModal(false);
      await fetchConnections();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to add MCP connection'
      );
    } finally {
      setOperationLoading(false);
    }
  };

  const handleTestConnection = (connection: TenantMCPIntegration) => {
    setSelectedConnection(connection);
    setShowTestModal(true);
  };

  const handleDiscoverTools = (connection: TenantMCPIntegration) => {
    setSelectedConnection(connection);
    setShowDiscoverModal(true);
  };

  const handleDeleteConnection = (connection: TenantMCPIntegration) => {
    setDeleteConfirmConnection(connection);
  };

  const handleConfirmDelete = async () => {
    if (!deleteConfirmConnection) return;

    setOperationLoading(true);
    try {
      await apiClient.deleteIntegration(deleteConfirmConnection.id);
      setSuccessMessage('MCP connection deleted successfully');
      setDeleteConfirmConnection(null);
      // If on last page and last item, go to previous page; otherwise stay on current
      const newTotal = total - 1;
      const newTotalPages = Math.ceil(newTotal / DEFAULT_LIMIT);
      if (page > newTotalPages && newTotalPages > 0) {
        setPage(newTotalPages);
      }
      await fetchConnections();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to delete MCP connection'
      );
    } finally {
      setOperationLoading(false);
    }
  };

  const handleToggleStatus = async (connection: TenantMCPIntegration) => {
    setOperationLoading(true);
    try {
      if (connection.is_enabled) {
        await apiClient.disableIntegration(connection.id);
        setSuccessMessage('MCP connection disabled');
      } else {
        await apiClient.enableIntegration(connection.id);
        setSuccessMessage('MCP connection enabled');
      }
      await fetchConnections();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to update MCP connection status'
      );
    } finally {
      setOperationLoading(false);
    }
  };

  const handleFilterChange = (newFilters: Filters) => {
    if (operationLoading || loading) return;
    setFilters(newFilters);
    setPage(1); // Reset to first page on filter change
  };

  const handleClearFilters = () => {
    if (operationLoading || loading) return;
    setFilters({
      search: '',
      auth_type: 'all',
      enabled: 'all',
    });
    setPage(1);
  };

  const totalPages = Math.ceil(total / DEFAULT_LIMIT);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      {/* Page Header */}
      <div className="mb-8 flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">MCP Connections</h1>
          <p className="mt-2 text-sm text-gray-600">
            Configure and manage external MCP server integrations
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700"
        >
          Add Connection
        </button>
      </div>

      {/* Success Message */}
      {successMessage && (
        <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-sm text-green-800">{successMessage}</p>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex justify-between items-center">
            <p className="text-sm text-red-800">{error}</p>
            <button
              onClick={() => setError(null)}
              className="text-red-600 hover:text-red-800 text-sm font-medium"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Connections List */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200">
        {/* Summary */}
        <div className="px-6 py-4 border-b border-gray-200">
          <p className="text-sm text-gray-600">
            {loading ? 'Loading...' : `Showing ${connections.length} of ${total} connections`}
          </p>
        </div>

        {/* Connections Table */}
        {connections.length > 0 ? (
          <>
            <MCPConnectionsList
              connections={connections}
              onTest={handleTestConnection}
              onDiscoverTools={handleDiscoverTools}
              onDelete={handleDeleteConnection}
              onToggleStatus={handleToggleStatus}
              loading={loading || operationLoading}
            />

            {/* Pagination */}
            <div className="px-6 py-4 border-t border-gray-200 flex items-center justify-between">
              <button
                onClick={() => setPage(page - 1)}
                disabled={page === 1 || loading || operationLoading}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>

              <div className="text-sm text-gray-600">
                Page {page} of {totalPages}
              </div>

              <button
                onClick={() => setPage(page + 1)}
                disabled={page >= totalPages || loading || operationLoading}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </>
        ) : loading ? (
          <div className="px-6 py-12 text-center">
            <div className="inline-block">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
          </div>
        ) : (
          <div className="px-6 py-12 text-center">
            <p className="text-gray-500">No MCP connections configured</p>
          </div>
        )}
      </div>

      {/* Modals */}
      <AddMCPModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onAdd={handleAddConnection}
        loading={operationLoading}
      />

      <TestConnectionModal
        isOpen={showTestModal}
        connection={selectedConnection}
        onClose={() => {
          setShowTestModal(false);
          setSelectedConnection(null);
        }}
        loading={operationLoading}
      />

      <DiscoverToolsModal
        isOpen={showDiscoverModal}
        connection={selectedConnection}
        onClose={() => {
          setShowDiscoverModal(false);
          setSelectedConnection(null);
        }}
      />

      <DeleteConnectionConfirm
        isOpen={deleteConfirmConnection !== null}
        connection={deleteConfirmConnection}
        onConfirm={handleConfirmDelete}
        onCancel={() => setDeleteConfirmConnection(null)}
        loading={operationLoading}
      />
    </div>
  );
}
