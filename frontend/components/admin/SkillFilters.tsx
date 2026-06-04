'use client';

interface SkillFiltersProps {
  filters: {
    search: string;
    status: 'all' | 'active' | 'inactive';
  };
  onFilterChange: (filters: { search: string; status: 'all' | 'active' | 'inactive' }) => void;
  onClearFilters: () => void;
  loading: boolean;
}

export default function SkillFilters({
  filters,
  onFilterChange,
  onClearFilters,
  loading,
}: SkillFiltersProps) {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Filters</h2>

      <div className="space-y-4">
        {/* Search */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Search by Name
          </label>
          <input
            type="text"
            value={filters.search}
            onChange={(e) =>
              onFilterChange({
                ...filters,
                search: e.target.value,
              })
            }
            placeholder="Filter skills..."
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        {/* Status */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Status
          </label>
          <select
            value={filters.status}
            onChange={(e) =>
              onFilterChange({
                ...filters,
                status: e.target.value as 'all' | 'active' | 'inactive',
              })
            }
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
          >
            <option value="all">All Skills</option>
            <option value="active">Active Only</option>
            <option value="inactive">Inactive Only</option>
          </select>
        </div>

        {/* Clear Filters */}
        <button
          onClick={onClearFilters}
          disabled={loading}
          className="w-full px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Clear Filters
        </button>
      </div>
    </div>
  );
}
