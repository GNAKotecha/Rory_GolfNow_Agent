'use client';

import { ChangeEvent } from 'react';

interface TraceFiltarsProps {
  filters: {
    trace_id: string;
    user_id: string;
    status: string | 'all';
    start_date: string;
    end_date: string;
    name: string;
  };
  onFilterChange: (filters: any) => void;
  onClearFilters: () => void;
  loading: boolean;
}

const STATUS_OPTIONS = [
  { value: 'all', label: 'All Status' },
  { value: 'success', label: 'Success' },
  { value: 'error', label: 'Error' },
  { value: 'timeout', label: 'Timeout' },
  { value: 'validation_error', label: 'Validation Error' },
];

export default function TraceFiltersPanel({
  filters,
  onFilterChange,
  onClearFilters,
  loading,
}: TraceFiltarsProps) {
  const handleChange = (
    key: keyof typeof filters,
    value: string
  ) => {
    onFilterChange({
      ...filters,
      [key]: value,
    });
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-6">Filters</h2>

      <div className="space-y-5">
        {/* Trace ID Search */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Trace ID
          </label>
          <input
            type="text"
            placeholder="Search by trace ID"
            value={filters.trace_id}
            onChange={(e) => handleChange('trace_id', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {/* User ID Filter */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            User ID
          </label>
          <input
            type="text"
            placeholder="Filter by user ID"
            value={filters.user_id}
            onChange={(e) => handleChange('user_id', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {/* Status Filter */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Status
          </label>
          <select
            value={filters.status}
            onChange={(e) => handleChange('status', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Workflow Name Filter */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Workflow Name
          </label>
          <input
            type="text"
            placeholder="Filter by workflow name"
            value={filters.name}
            onChange={(e) => handleChange('name', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {/* Start Date */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Start Date
          </label>
          <input
            type="datetime-local"
            value={filters.start_date}
            onChange={(e) => handleChange('start_date', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {/* End Date */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            End Date
          </label>
          <input
            type="datetime-local"
            value={filters.end_date}
            onChange={(e) => handleChange('end_date', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {/* Button Group */}
        <div className="space-y-3 pt-4 border-t border-gray-200">
          <button
            onClick={onClearFilters}
            disabled={loading}
            className="w-full px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Clear Filters
          </button>
        </div>
      </div>
    </div>
  );
}
