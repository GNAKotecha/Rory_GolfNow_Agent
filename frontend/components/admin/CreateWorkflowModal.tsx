'use client';

import { useState } from 'react';

interface CreateWorkflowModalProps {
  onSave: (data: any) => Promise<void>;
  onClose: () => void;
  loading?: boolean;
}

export default function CreateWorkflowModal({ onSave, onClose, loading = false }: CreateWorkflowModalProps) {
  const [formData, setFormData] = useState({
    workflow_name: '',
    description: '',
    definition: '{}'
  });
  const [error, setError] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);

  const validateJSON = (str: string): boolean => {
    try {
      JSON.parse(str);
      return true;
    } catch {
      return false;
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    setError(null);
  };

  const handleDefinitionBlur = () => {
    if (formData.definition && !validateJSON(formData.definition)) {
      setError('Invalid JSON in workflow definition');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.workflow_name.trim()) {
      setError('Workflow name is required');
      return;
    }

    if (!validateJSON(formData.definition)) {
      setError('Invalid JSON in workflow definition');
      return;
    }

    try {
      setValidating(true);
      const payload = {
        workflow_name: formData.workflow_name,
        description: formData.description,
        definition: JSON.parse(formData.definition)
      };
      await onSave(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create workflow');
    } finally {
      setValidating(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-96 overflow-y-auto">
        <div className="border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Create Workflow</h2>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-800">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Workflow Name *
            </label>
            <input
              type="text"
              name="workflow_name"
              value={formData.workflow_name}
              onChange={handleChange}
              placeholder="e.g., Onboarding Flow"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              name="description"
              value={formData.description}
              onChange={handleChange}
              placeholder="Workflow description..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              rows={2}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Workflow Definition (JSON) *
            </label>
            <textarea
              name="definition"
              value={formData.definition}
              onChange={handleChange}
              onBlur={handleDefinitionBlur}
              placeholder='{"steps": []}'
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
              rows={6}
              required
            />
            <p className="text-xs text-gray-500 mt-1">Enter valid JSON</p>
          </div>

          <div className="flex gap-3 pt-4 border-t border-gray-200">
            <button
              type="button"
              onClick={onClose}
              disabled={loading || validating}
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || validating}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {loading || validating ? 'Creating...' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
