'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';
import WorkflowsList from '@/components/admin/WorkflowsList';
import CreateWorkflowModal from '@/components/admin/CreateWorkflowModal';
import EditWorkflowModal from '@/components/admin/EditWorkflowModal';
import DeleteWorkflowConfirm from '@/components/admin/DeleteWorkflowConfirm';

interface Workflow {
  id: number;
  tenant_id?: number;
  workflow_name: string;
  description: string | null;
  definition?: Record<string, any>;
  workflow_definition?: Record<string, any>;
  version: number;
  is_active: boolean;
  active_version?: number | null;
  created_at: string;
  updated_at: string;
  created_by?: number | null;
}

interface SuccessMessage {
  text: string;
  type: 'create' | 'update' | 'delete' | 'toggle';
}

const DEFAULT_LIMIT = 20;

export default function WorkflowsPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<SuccessMessage | null>(null);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(null);

  useEffect(() => {
    if (!authLoading && (!user || user.role !== 'admin')) {
      router.push('/');
      return;
    }
    if (!authLoading) {
      fetchWorkflows();
    }
  }, [user, authLoading, router]);

  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [successMessage]);

  const fetchWorkflows = async () => {
    setLoading(true);
    try {
      const data = await apiClient.getWorkflows();
      setWorkflows(Array.isArray(data) ? data : data.workflows || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load workflows');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateWorkflow = async (payload: any) => {
    try {
      const newWorkflow = await apiClient.createWorkflow(payload);
      setWorkflows([newWorkflow, ...workflows]);
      setShowCreateModal(false);
      setSuccessMessage({ text: 'Workflow created successfully', type: 'create' });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create workflow');
    }
  };

  const handleEditWorkflow = async (id: number, payload: any) => {
    try {
      const updated = await apiClient.updateWorkflow(id, payload);
      setWorkflows(workflows.map(w => w.id === id ? updated : w));
      setShowEditModal(false);
      setSelectedWorkflow(null);
      setSuccessMessage({ text: 'Workflow updated successfully', type: 'update' });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update workflow');
    }
  };

  const handleDeleteWorkflow = async (id: number) => {
    try {
      await apiClient.deleteWorkflow(id);
      setWorkflows(workflows.filter(w => w.id !== id));
      setShowDeleteConfirm(false);
      setSelectedWorkflow(null);
      setSuccessMessage({ text: 'Workflow deleted successfully', type: 'delete' });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete workflow');
    }
  };

  const handleToggleStatus = async (workflow: Workflow) => {
    try {
      if (workflow.is_active) {
        await apiClient.deactivateWorkflow(workflow.id);
      } else {
        await apiClient.activateWorkflow(workflow.id);
      }
      setWorkflows(workflows.map(w =>
        w.id === workflow.id ? { ...w, is_active: !w.is_active } : w
      ));
      setSuccessMessage({
        text: `Workflow ${!workflow.is_active ? 'activated' : 'deactivated'} successfully`,
        type: 'toggle'
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update workflow status');
    }
  };

  if (authLoading || !user) return null;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Workflows</h1>
        <p className="mt-2 text-sm text-gray-600">Manage workflow templates and configurations</p>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex justify-between items-center">
          <p className="text-sm text-red-800">{error}</p>
          <button
            onClick={() => setError(null)}
            className="text-red-600 hover:text-red-700 font-medium"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Success Message */}
      {successMessage && (
        <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-sm text-green-800">{successMessage.text}</p>
        </div>
      )}

      {/* Create Button */}
      <div className="mb-6">
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
        >
          + Create Workflow
        </button>
      </div>

      {/* Workflows List */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200">
        {loading ? (
          <div className="p-8 text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p className="mt-2 text-gray-500">Loading workflows...</p>
          </div>
        ) : workflows.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            <p>No workflows found. Create one to get started.</p>
          </div>
        ) : (
          <WorkflowsList
            workflows={workflows}
            onEdit={(workflow) => {
              setSelectedWorkflow(workflow);
              setShowEditModal(true);
            }}
            onDelete={(workflow) => {
              setSelectedWorkflow(workflow);
              setShowDeleteConfirm(true);
            }}
            onToggleStatus={handleToggleStatus}
            loading={loading}
          />
        )}
      </div>

      {/* Modals */}
      {showCreateModal && (
        <CreateWorkflowModal
          onSave={handleCreateWorkflow}
          onClose={() => setShowCreateModal(false)}
          loading={loading}
        />
      )}

      {showEditModal && selectedWorkflow && (
        <EditWorkflowModal
          workflow={selectedWorkflow}
          onSave={(payload) => handleEditWorkflow(selectedWorkflow.id, payload)}
          onClose={() => {
            setShowEditModal(false);
            setSelectedWorkflow(null);
          }}
          loading={loading}
        />
      )}

      {showDeleteConfirm && selectedWorkflow && (
        <DeleteWorkflowConfirm
          workflow={selectedWorkflow}
          onConfirm={() => handleDeleteWorkflow(selectedWorkflow.id)}
          onCancel={() => {
            setShowDeleteConfirm(false);
            setSelectedWorkflow(null);
          }}
          loading={loading}
        />
      )}
    </div>
  );
}
