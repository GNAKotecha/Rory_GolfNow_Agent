'use client';

import { useState, useEffect } from 'react';
import { apiClient, TenantSkill, TenantSkillCreate } from '@/lib/api';
import SkillsList from '@/components/admin/SkillsList';
import SkillFilters from '@/components/admin/SkillFilters';
import CreateSkillModal from '@/components/admin/CreateSkillModal';
import EditSkillModal from '@/components/admin/EditSkillModal';
import DeleteSkillConfirm from '@/components/admin/DeleteSkillConfirm';

const DEFAULT_LIMIT = 20;

export default function SkillsManagementPage() {
  // Filter state
  const [filters, setFilters] = useState({
    search: '',
    status: 'all' as 'all' | 'active' | 'inactive',
  });

  // Data state
  const [skills, setSkills] = useState<TenantSkill[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingSkill, setEditingSkill] = useState<TenantSkill | null>(null);
  const [deleteConfirmSkill, setDeleteConfirmSkill] = useState<TenantSkill | null>(null);
  const [operationLoading, setOperationLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Fetch skills when filters or page changes
  useEffect(() => {
    fetchSkills();
  }, [page, filters]);

  // Clear success message after 3 seconds
  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [successMessage]);

  const fetchSkills = async () => {
    setLoading(true);
    setError(null);

    try {
      const offset = (page - 1) * DEFAULT_LIMIT;
      const response = await apiClient.getSkills(DEFAULT_LIMIT, offset);

      // Apply client-side filtering for search and status
      let filtered = response.skills;

      if (filters.search) {
        const searchLower = filters.search.toLowerCase();
        filtered = filtered.filter(
          (skill) =>
            skill.skill_name.toLowerCase().includes(searchLower) ||
            (skill.description?.toLowerCase() ?? '').includes(searchLower)
        );
      }

      if (filters.status !== 'all') {
        const isActive = filters.status === 'active';
        filtered = filtered.filter((skill) => skill.is_active === isActive);
      }

      setSkills(filtered);
      setTotal(response.total || filtered.length);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to fetch skills'
      );
      setSkills([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  const handleFilterChange = (newFilters: typeof filters) => {
    setFilters(newFilters);
    setPage(1);
  };

  const handleClearFilters = () => {
    setFilters({
      search: '',
      status: 'all',
    });
    setPage(1);
  };

  const handleCreateSkill = async (data: TenantSkillCreate) => {
    setOperationLoading(true);
    try {
      await apiClient.createSkill(data);
      setSuccessMessage('Skill created successfully');
      setShowCreateModal(false);
      setPage(1);
      // Skip re-filter since we just created and moved to page 1
      const response = await apiClient.getSkills(DEFAULT_LIMIT, 0);
      setSkills(response.skills);
      setTotal(response.total || response.skills.length);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to create skill'
      );
    } finally {
      setOperationLoading(false);
    }
  };

  const handleEditSkill = (skill: TenantSkill) => {
    setEditingSkill(skill);
    setShowEditModal(true);
  };

  const handleSaveSkill = async (data: Partial<TenantSkill>) => {
    if (!editingSkill) return;

    setOperationLoading(true);
    try {
      await apiClient.updateSkill(editingSkill.id, data);
      setSuccessMessage('Skill updated successfully');
      setShowEditModal(false);
      setEditingSkill(null);
      // Refresh current page without re-filtering
      const offset = (page - 1) * DEFAULT_LIMIT;
      const response = await apiClient.getSkills(DEFAULT_LIMIT, offset);
      setSkills(response.skills);
      setTotal(response.total || response.skills.length);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to update skill'
      );
    } finally {
      setOperationLoading(false);
    }
  };

  const handleDeleteSkill = (skill: TenantSkill) => {
    setDeleteConfirmSkill(skill);
  };

  const handleConfirmDelete = async () => {
    if (!deleteConfirmSkill) return;

    setOperationLoading(true);
    try {
      await apiClient.deleteSkill(deleteConfirmSkill.id);
      setSuccessMessage('Skill deleted successfully');
      setDeleteConfirmSkill(null);
      setPage(1);
      // Skip re-filter since we're already on page 1
      const response = await apiClient.getSkills(DEFAULT_LIMIT, 0);
      setSkills(response.skills);
      setTotal(response.total || response.skills.length);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to delete skill'
      );
    } finally {
      setOperationLoading(false);
    }
  };

  const handleToggleStatus = async (skill: TenantSkill) => {
    setOperationLoading(true);
    try {
      if (skill.is_active) {
        await apiClient.deactivateSkill(skill.id);
        setSuccessMessage('Skill deactivated');
      } else {
        await apiClient.activateSkill(skill.id);
        setSuccessMessage('Skill activated');
      }
      // Refresh current page without re-filtering
      const offset = (page - 1) * DEFAULT_LIMIT;
      const response = await apiClient.getSkills(DEFAULT_LIMIT, offset);
      setSkills(response.skills);
      setTotal(response.total || response.skills.length);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to update skill status'
      );
    } finally {
      setOperationLoading(false);
    }
  };

  const totalPages = Math.ceil(total / DEFAULT_LIMIT);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      {/* Page Header */}
      <div className="mb-8 flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Skills Management</h1>
          <p className="mt-2 text-sm text-gray-600">
            Create, manage, and configure tenant skills
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700"
        >
          Create Skill
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

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Filter Panel */}
        <div className="lg:col-span-1">
          <SkillFilters
            filters={filters}
            onFilterChange={handleFilterChange}
            onClearFilters={handleClearFilters}
            loading={loading || operationLoading}
          />
        </div>

        {/* Skills List */}
        <div className="lg:col-span-3">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200">
            {/* Summary */}
            <div className="px-6 py-4 border-b border-gray-200">
              <p className="text-sm text-gray-600">
                {loading ? 'Loading...' : `Showing ${skills.length} of ${total} skills`}
              </p>
            </div>

            {/* Skills Table */}
            {skills.length > 0 ? (
              <>
                <SkillsList
                  skills={skills}
                  onEdit={handleEditSkill}
                  onDelete={handleDeleteSkill}
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
                <p className="text-gray-500">No skills found</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Modals */}
      <CreateSkillModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreate={handleCreateSkill}
        loading={operationLoading}
      />

      <EditSkillModal
        isOpen={showEditModal}
        skill={editingSkill}
        onClose={() => {
          setShowEditModal(false);
          setEditingSkill(null);
        }}
        onSave={handleSaveSkill}
        loading={operationLoading}
      />

      <DeleteSkillConfirm
        isOpen={deleteConfirmSkill !== null}
        skill={deleteConfirmSkill}
        onConfirm={handleConfirmDelete}
        onCancel={() => setDeleteConfirmSkill(null)}
        loading={operationLoading}
      />
    </div>
  );
}
