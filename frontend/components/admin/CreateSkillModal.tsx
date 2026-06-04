'use client';

import { useState } from 'react';
import { TenantSkillCreate } from '@/lib/api';
import {
  resetSkillForm,
  validateSkillJSON,
  SkillFormData,
} from './skillFormUtils';

interface CreateSkillModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (data: TenantSkillCreate) => Promise<void>;
  loading: boolean;
}

export default function CreateSkillModal({
  isOpen,
  onClose,
  onCreate,
  loading,
}: CreateSkillModalProps) {
  const [formData, setFormData] = useState<SkillFormData>(resetSkillForm());
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [jsonValidated, setJsonValidated] = useState(false);

  if (!isOpen) return null;

  const handleValidateJSON = (): boolean => {
    const result = validateSkillJSON(formData.skill_data);
    if (result.valid) {
      setValidationError(null);
      setJsonValidated(true);
      return true;
    } else {
      setValidationError(result.error);
      setJsonValidated(false);
      return false;
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validate required fields
    if (!formData.skill_name.trim()) {
      setError('Skill name is required');
      return;
    }

    // Skip JSON validation on submit if already validated on blur
    if (!jsonValidated && !handleValidateJSON()) {
      return;
    }

    try {
      await onCreate({
        skill_name: formData.skill_name,
        description: formData.description,
        skill_data: JSON.parse(formData.skill_data),
      });
      setFormData(resetSkillForm());
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create skill');
    }
  };

  const handleClose = () => {
    setFormData(resetSkillForm());
    setError(null);
    setValidationError(null);
    setJsonValidated(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h2 className="text-lg font-semibold text-gray-900">Create New Skill</h2>
          <button
            onClick={handleClose}
            className="text-gray-500 hover:text-gray-700"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Error Message */}
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-800">
              {error}
            </div>
          )}

          {/* Skill Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Skill Name *
            </label>
            <input
              type="text"
              value={formData.skill_name}
              onChange={(e) =>
                setFormData({ ...formData, skill_name: e.target.value })
              }
              placeholder="e.g., email_validator"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              value={formData.description}
              onChange={(e) =>
                setFormData({ ...formData, description: e.target.value })
              }
              placeholder="Brief description of what this skill does"
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Skill Data JSON */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Skill Data (JSON) *
            </label>
            <div className="relative">
              <textarea
                value={formData.skill_data}
                onChange={(e) => {
                  setFormData({ ...formData, skill_data: e.target.value });
                  setValidationError(null);
                  setJsonValidated(false);
                }}
                onBlur={handleValidateJSON}
                placeholder='{"type": "custom", "config": {}}'
                rows={10}
                className={`w-full px-3 py-2 border rounded-md text-sm font-mono focus:outline-none focus:ring-blue-500 focus:border-blue-500 ${
                  validationError ? 'border-red-300' : 'border-gray-300'
                }`}
              />
              {validationError && (
                <p className="mt-1 text-sm text-red-600">{validationError}</p>
              )}
            </div>
            <p className="mt-1 text-xs text-gray-500">
              Enter valid JSON configuration for the skill
            </p>
          </div>

          {/* Buttons */}
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
            <button
              type="button"
              onClick={handleClose}
              disabled={loading}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Creating...' : 'Create Skill'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
