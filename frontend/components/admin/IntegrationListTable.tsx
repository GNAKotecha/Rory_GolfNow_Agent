'use client';

import { TenantMCPIntegration, HealthCheckResponse } from '@/lib/api';

interface IntegrationListTableProps {
  integrations: TenantMCPIntegration[];
  healthStatus: Record<number, HealthCheckResponse | null>;
  onEdit: (integration: TenantMCPIntegration) => void;
  onDelete: (integration: TenantMCPIntegration) => void;
  onTest: (id: number) => void;
  onToggleEnable: (id: number, enabled: boolean) => void;
  loading: boolean;
  itemsPerPage: number;
  currentPage: number;
  onPageChange: (page: number) => void;
}

const HEALTH_COLORS: Record<string, { bg: string; text: string; badge: string; dot: string }> = {
  healthy: {
    bg: 'bg-green-50',
    text: 'text-green-800',
    badge: 'bg-green-100',
    dot: 'bg-green-500',
  },
  unhealthy: {
    bg: 'bg-red-50',
    text: 'text-red-800',
    badge: 'bg-red-100',
    dot: 'bg-red-500',
  },
  unknown: {
    bg: 'bg-yellow-50',
    text: 'text-yellow-800',
    badge: 'bg-yellow-100',
    dot: 'bg-yellow-500',
  },
  not_tested: {
    bg: 'bg-gray-50',
    text: 'text-gray-800',
    badge: 'bg-gray-100',
    dot: 'bg-gray-400',
  },
};

const formatAuthType = (authType: string): string => {
  const mapping: Record<string, string> = {
    oauth: 'OAuth',
    api_key: 'API Key',
    pat: 'PAT',
  };
  return mapping[authType] || authType;
};

const formatDate = (dateString: string): string => {
  const date = new Date(dateString);
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const getHealthStatus = (health: HealthCheckResponse | null | undefined): string => {
  if (!health) return 'not_tested';
  return health.status;
};

export default function IntegrationListTable({
  integrations,
  healthStatus,
  onEdit,
  onDelete,
  onTest,
  onToggleEnable,
  loading,
  itemsPerPage,
  currentPage,
  onPageChange,
}: IntegrationListTableProps) {
  // Pagination
  const totalPages = Math.ceil(integrations.length / itemsPerPage);
  const start = (currentPage - 1) * itemsPerPage;
  const paginatedIntegrations = integrations.slice(
    start,
    start + itemsPerPage
  );

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Auth Type
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Enabled
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Health Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Created
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {paginatedIntegrations.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-sm text-gray-500">
                  No integrations found
                </td>
              </tr>
            ) : (
              paginatedIntegrations.map((integration) => {
                const health = healthStatus[integration.id];
                const healthStatusKey = getHealthStatus(health);
                const healthColors = HEALTH_COLORS[healthStatusKey] || HEALTH_COLORS.not_tested;

                return (
                  <tr key={integration.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {integration.integration_name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {formatAuthType(integration.auth_type)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <button
                        onClick={() => onToggleEnable(integration.id, !integration.is_enabled)}
                        disabled={loading}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                          integration.is_enabled ? 'bg-blue-600' : 'bg-gray-300'
                        } disabled:opacity-50 disabled:cursor-not-allowed`}
                      >
                        <span
                          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                            integration.is_enabled ? 'translate-x-6' : 'translate-x-1'
                          }`}
                        />
                      </button>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <span className={`inline-block h-2 w-2 rounded-full ${healthColors.dot}`} />
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${healthColors.badge} ${healthColors.text}`}>
                          {healthStatusKey === 'not_tested'
                            ? 'Not Tested'
                            : healthStatusKey.charAt(0).toUpperCase() + healthStatusKey.slice(1)}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {formatDate(integration.created_at)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                      <button
                        onClick={() => onEdit(integration)}
                        disabled={loading}
                        className="text-blue-600 hover:text-blue-800 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => onTest(integration.id)}
                        disabled={loading}
                        className="text-green-600 hover:text-green-800 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Test
                      </button>
                      <button
                        onClick={() => onDelete(integration)}
                        disabled={loading}
                        className="text-red-600 hover:text-red-800 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between border-t border-gray-200 pt-4">
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">Items per page:</label>
          <select
            value={itemsPerPage}
            onChange={(e) => {
              // This would need to be passed back through page
              onPageChange(1);
            }}
            className="px-2 py-1 border border-gray-300 rounded text-sm"
          >
            <option value={10}>10</option>
            <option value={25}>25</option>
            <option value={50}>50</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage === 1 || loading}
            className="px-3 py-1 border border-gray-300 rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
          >
            Previous
          </button>
          <span className="text-sm text-gray-600">
            Page {currentPage} of {totalPages || 1}
          </span>
          <button
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage >= totalPages || loading}
            className="px-3 py-1 border border-gray-300 rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
