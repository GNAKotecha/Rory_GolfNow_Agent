'use client';

const formatDistanceToNow = (dateString: string): string => {
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
};

interface Workflow {
  id: number;
  tenant_id?: number;
  workflow_name: string;
  description: string;
  definition?: Record<string, any>;
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  created_by?: number;
}

interface WorkflowsListProps {
  workflows: Workflow[];
  onEdit: (workflow: Workflow) => void;
  onDelete: (workflow: Workflow) => void;
  onToggleStatus: (workflow: Workflow) => void;
  loading?: boolean;
}

export default function WorkflowsList({
  workflows,
  onEdit,
  onDelete,
  onToggleStatus,
  loading = false
}: WorkflowsListProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Description</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Version</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Updated</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {workflows.map((workflow) => (
            <tr key={workflow.id} className="hover:bg-gray-50">
              <td className="px-6 py-4 whitespace-nowrap">
                <div className="text-sm font-medium text-gray-900">{workflow.workflow_name}</div>
                <div className="text-xs text-gray-500">ID: {workflow.id}</div>
              </td>
              <td className="px-6 py-4">
                <div className="text-sm text-gray-600 max-w-xs truncate">{workflow.description || '—'}</div>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">v{workflow.version}</td>
              <td className="px-6 py-4 whitespace-nowrap">
                <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                  workflow.is_active
                    ? 'bg-green-100 text-green-800'
                    : 'bg-gray-100 text-gray-800'
                }`}>
                  {workflow.is_active ? 'Active' : 'Inactive'}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                {formatDistanceToNow(workflow.updated_at)}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                <button
                  onClick={() => onToggleStatus(workflow)}
                  disabled={loading}
                  className="text-blue-600 hover:text-blue-700 disabled:opacity-50"
                >
                  {workflow.is_active ? 'Disable' : 'Enable'}
                </button>
                <button
                  onClick={() => onEdit(workflow)}
                  disabled={loading}
                  className="text-gray-600 hover:text-gray-700 disabled:opacity-50"
                >
                  Edit
                </button>
                <button
                  onClick={() => onDelete(workflow)}
                  disabled={loading}
                  className="text-red-600 hover:text-red-700 disabled:opacity-50"
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
