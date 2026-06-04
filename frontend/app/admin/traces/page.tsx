'use client';

import { useState, useEffect } from 'react';
import { apiClient, TracePreview, TraceDetail } from '@/lib/api';
import TraceFiltersPanel from '@/components/admin/TraceFiltersPanel';
import TraceListTable from '@/components/admin/TraceListTable';
import TraceDetailModal from '@/components/admin/TraceDetailModal';

const DEFAULT_LIMIT = 20;

export default function TraceExplorerPage() {
  // Filter state
  const [filters, setFilters] = useState({
    trace_id: '',
    user_id: '',
    status: 'all' as string | 'all',
    start_date: '',
    end_date: '',
    name: '',
  });

  // Data state
  const [traces, setTraces] = useState<TracePreview[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Detail modal state
  const [selectedTrace, setSelectedTrace] = useState<TraceDetail | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  // Fetch traces when filters or page changes
  useEffect(() => {
    fetchTraces();
  }, [page, filters]);

  const fetchTraces = async () => {
    setLoading(true);
    setError(null);

    try {
      const offset = (page - 1) * DEFAULT_LIMIT;
      const apiFilters: any = {
        limit: DEFAULT_LIMIT,
        offset,
      };

      if (filters.trace_id) {
        apiFilters.trace_id = filters.trace_id;
      }
      if (filters.user_id) {
        apiFilters.user_id = filters.user_id;
      }
      if (filters.status && filters.status !== 'all') {
        apiFilters.status = filters.status;
      }
      if (filters.start_date) {
        apiFilters.start_date = filters.start_date;
      }
      if (filters.end_date) {
        apiFilters.end_date = filters.end_date;
      }
      if (filters.name) {
        apiFilters.name = filters.name;
      }

      const response = await apiClient.getTraces(apiFilters);
      setTraces(response.traces);
      setTotal(response.total);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to fetch traces'
      );
      setTraces([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  const handleFilterChange = (newFilters: typeof filters) => {
    setFilters(newFilters);
    setPage(1); // Reset to first page on filter change
  };

  const handleClearFilters = () => {
    setFilters({
      trace_id: '',
      user_id: '',
      status: 'all',
      start_date: '',
      end_date: '',
      name: '',
    });
    setPage(1);
  };

  const handleViewTrace = async (traceId: string) => {
    setDetailLoading(true);
    try {
      const detail = await apiClient.getTrace(traceId);
      setSelectedTrace(detail);
      setShowDetail(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to fetch trace details'
      );
    } finally {
      setDetailLoading(false);
    }
  };

  const handleCloseDetail = () => {
    setShowDetail(false);
    setSelectedTrace(null);
  };

  const totalPages = Math.ceil(total / DEFAULT_LIMIT);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      {/* Page Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Trace Explorer</h1>
        <p className="mt-2 text-sm text-gray-600">
          View and explore all workflow execution traces from Langfuse
        </p>
      </div>

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
          <TraceFiltersPanel
            filters={filters}
            onFilterChange={handleFilterChange}
            onClearFilters={handleClearFilters}
            loading={loading}
          />
        </div>

        {/* Trace List */}
        <div className="lg:col-span-3">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200">
            {/* Summary */}
            <div className="px-6 py-4 border-b border-gray-200">
              <p className="text-sm text-gray-600">
                {loading ? 'Loading...' : `Showing ${traces.length} of ${total} traces`}
              </p>
            </div>

            {/* Trace Table */}
            {traces.length > 0 ? (
              <>
                <TraceListTable
                  traces={traces}
                  onViewTrace={handleViewTrace}
                  loading={loading}
                />

                {/* Pagination */}
                <div className="px-6 py-4 border-t border-gray-200 flex items-center justify-between">
                  <button
                    onClick={() => setPage(page - 1)}
                    disabled={page === 1 || loading}
                    className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>

                  <div className="text-sm text-gray-600">
                    Page {page} of {totalPages}
                  </div>

                  <button
                    onClick={() => setPage(page + 1)}
                    disabled={page >= totalPages || loading}
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
                <p className="text-gray-500">No traces found</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Trace Detail Modal */}
      {showDetail && (
        <TraceDetailModal
          trace={selectedTrace}
          onClose={handleCloseDetail}
          loading={detailLoading}
        />
      )}
    </div>
  );
}
