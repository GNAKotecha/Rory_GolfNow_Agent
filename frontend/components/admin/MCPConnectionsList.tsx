'use client';

import { TenantMCPIntegration } from '@/lib/api';

interface MCPConnectionsListProps {
  connections: TenantMCPIntegration[];
  onTest: (connection: TenantMCPIntegration) => void;
  onDiscoverTools: (connection: TenantMCPIntegration) => void;
  onDelete: (connection: TenantMCPIntegration) => void;
  onToggleStatus: (connection: TenantMCPIntegration) => void;
  loading: boolean;
}

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

const getAuthTypeBadgeColor = (authType: string): string => {
  switch (authType) {
    case 'oauth':
      return 'bg-blue-100 text-blue-800';
    case 'api_key':
      return 'bg-purple-100 text-purple-800';
    case 'pat':
      return 'bg-green-100 text-green-800';
    default:
      return 'bg-gray-100 text-gray-800';
  }
};

export default function MCPConnectionsList({
  connections,
  onTest,
  onDiscoverTools,
  onDelete,
  onToggleStatus,
  loading,
}: MCPConnectionsListProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50">
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Connection Name
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Auth Type
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Status
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Updated
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {connections.map((connection) => (
            <tr key={connection.id} className="hover:bg-gray-50">
              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                {connection.integration_name}
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <span
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getAuthTypeBadgeColor(
                    connection.auth_type
                  )}`}
                >
                  {connection.auth_type === 'api_key' ? 'API Key' : connection.auth_type.toUpperCase()}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <span
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    connection.is_enabled
                      ? 'bg-green-100 text-green-800'
                      : 'bg-gray-100 text-gray-800'
                  }`}
                >
                  {connection.is_enabled ? 'Enabled' : 'Disabled'}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                {formatDate(connection.updated_at)}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                <button
                  onClick={() => onTest(connection)}
                  disabled={loading}
                  className="text-blue-600 hover:text-blue-800 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Test
                </button>
                <button
                  onClick={() => onDiscoverTools(connection)}
                  disabled={loading}
                  className="text-green-600 hover:text-green-800 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Tools
                </button>
                <button
                  onClick={() => onToggleStatus(connection)}
                  disabled={loading}
                  className="text-amber-600 hover:text-amber-800 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {connection.is_enabled ? 'Disable' : 'Enable'}
                </button>
                <button
                  onClick={() => onDelete(connection)}
                  disabled={loading}
                  className="text-red-600 hover:text-red-800 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
