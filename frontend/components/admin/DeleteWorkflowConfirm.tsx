'use client';

interface Workflow {
  id: number;
  workflow_name: string;
  version: number;
  is_active: boolean;
}

interface DeleteWorkflowConfirmProps {
  workflow: Workflow;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
}

export default function DeleteWorkflowConfirm({
  workflow,
  onConfirm,
  onCancel,
  loading = false
}: DeleteWorkflowConfirmProps) {
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full">
        <div className="border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Delete Workflow</h2>
        </div>

        <div className="p-6 space-y-4">
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-800">
              <strong>Warning:</strong> This action cannot be undone.
            </p>
          </div>

          <div className="space-y-2">
            <p className="text-sm text-gray-700">
              Are you sure you want to delete this workflow?
            </p>
            <div className="bg-gray-50 p-3 rounded text-sm space-y-1">
              <p><strong>Name:</strong> {workflow.workflow_name}</p>
              <p><strong>ID:</strong> {workflow.id}</p>
              <p><strong>Version:</strong> {workflow.version}</p>
              <p><strong>Status:</strong> {workflow.is_active ? 'Active' : 'Inactive'}</p>
            </div>
          </div>

          <div className="flex gap-3 pt-4 border-t border-gray-200">
            <button
              onClick={onCancel}
              disabled={loading}
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              disabled={loading}
              className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
            >
              {loading ? 'Deleting...' : 'Delete'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
