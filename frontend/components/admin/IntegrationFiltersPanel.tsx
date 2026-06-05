'use client';

import { useEffect } from 'react';

interface Filters {
  search: string;
  auth_type: 'oauth' | 'api_key' | 'pat' | 'all';
  enabled: 'all' | 'true' | 'false';
}

interface IntegrationFiltersPanelProps {
  filters: Filters;
  onFilterChange: (filters: Filters) => void;
  onClearFilters: () => void;
  loading: boolean;
}

const AUTH_TYPE_OPTIONS = [
  { value: 'all', label: 'All Auth Types' },
  { value: 'oauth', label: 'OAuth' },
  { value: 'api_key', label: 'API Key' },
  { value: 'pat', label: 'Personal Access Token' },
];

export default function IntegrationFiltersPanel({
  filters,
  onFilterChange,
  onClearFilters,
  loading,
}: IntegrationFiltersPanelProps) {
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
    <div className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Filters</h3>

      <div className="space-y-4">
        {/* Search */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Integration Name
          </label>
          <input
            type="text"
            placeholder="Search by name..."
            value={filters.search}
            onChange={(e) => handleChange('search', e.target.value)}
            disabled={loading}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </div>

        {/* Auth Type */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Authentication Type
          </label>
          <select
            value={filters.auth_type}
            onChange={(e) => handleChange('auth_type', e.target.value)}
            disabled={loading}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed bg-white"
          >
            {AUTH_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Enabled Status */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Status
          </label>
          <div className="space-y-2">
            <label className="flex items-center">
              <input
                type="radio"
                name="enabled"
                value="all"
                checked={filters.enabled === 'all'}
                onChange={(e) => handleChange('enabled', e.target.value)}
                disabled={loading}
                className="h-4 w-4 text-blue-600 border-gray-300 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              />
              <span className="ml-3 text-sm text-gray-700">All</span>
            </label>
            <label className="flex items-center">
              <input
                type="radio"
                name="enabled"
                value="true"
                checked={filters.enabled === 'true'}
                onChange={(e) => handleChange('enabled', e.target.value)}
                disabled={loading}
                className="h-4 w-4 text-blue-600 border-gray-300 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              />
              <span className="ml-3 text-sm text-gray-700">Enabled</span>
            </label>
            <label className="flex items-center">
              <input
                type="radio"
                name="enabled"
                value="false"
                checked={filters.enabled === 'false'}
                onChange={(e) => handleChange('enabled', e.target.value)}
                disabled={loading}
                className="h-4 w-4 text-blue-600 border-gray-300 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              />
              <span className="ml-3 text-sm text-gray-700">Disabled</span>
            </label>
          </div>
        </div>

        {/* Clear Button */}
        <div className="pt-4 border-t border-gray-200">
          <button
            onClick={onClearFilters}
            disabled={loading}
            className="w-full px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Clear Filters
          </button>
        </div>
      </div>
    </div>
  );
}
