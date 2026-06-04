'use client';

import { TenantSkill } from '@/lib/api';

interface DeleteSkillConfirmProps {
  isOpen: boolean;
  skill: TenantSkill | null;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
  loading: boolean;
}

export default function DeleteSkillConfirm({
  isOpen,
  skill,
  onConfirm,
  onCancel,
  loading,
}: DeleteSkillConfirmProps) {
  if (!isOpen || !skill) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-sm w-full">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Delete Skill?</h2>
        </div>

        <div className="p-6 space-y-4">
          <div className="p-3 bg-yellow-50 border border-yellow-200 rounded text-sm text-yellow-800">
            Warning: This action cannot be undone.
          </div>

          <p className="text-sm text-gray-600">
            Are you sure you want to permanently delete the skill{' '}
            <span className="font-semibold text-gray-900">"{skill.skill_name}"</span>?
          </p>

          <div className="p-3 bg-gray-50 rounded text-xs text-gray-600 space-y-1">
            <p>
              <span className="font-medium">ID:</span> {skill.id}
            </p>
            <p>
              <span className="font-medium">Status:</span>{' '}
              {skill.is_active ? 'Active' : 'Inactive'}
            </p>
            <p>
              <span className="font-medium">Version:</span> {skill.version}
            </p>
          </div>
        </div>

        <div className="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
}
