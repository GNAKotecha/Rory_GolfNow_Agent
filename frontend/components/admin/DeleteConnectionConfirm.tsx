'use client';

import { TenantMCPIntegration } from '@/lib/api';

interface DeleteConnectionConfirmProps {
  isOpen: boolean;
  connection: TenantMCPIntegration | null;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
  loading: boolean;
}

export default function DeleteConnectionConfirm({
  isOpen,
  connection,
  onConfirm,
  onCancel,
  loading,
}: DeleteConnectionConfirmProps) {
  if (!isOpen || !connection) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-lg max-w-sm w-full mx-4">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Delete Connection</h2>
        </div>

        {/* Body */}
        <div className="px-6 py-4">
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
            <p className="text-sm text-red-700">
              Are you sure you want to delete <strong>{connection.integration_name}</strong>?
            </p>
          </div>
          <p className="text-sm text-gray-600 mb-2">This action cannot be undone.</p>
          <p className="text-xs text-gray-500">
            The connection and any stored credentials will be permanently removed.
          </p>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200 flex gap-3">
          <button
            onClick={onCancel}
            disabled={loading}
            className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex-1 px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
}
