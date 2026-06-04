'use client';

import { TenantSkill } from '@/lib/api';

interface SkillsListProps {
  skills: TenantSkill[];
  onEdit: (skill: TenantSkill) => void;
  onDelete: (skill: TenantSkill) => void;
  onToggleStatus: (skill: TenantSkill) => void;
  loading: boolean;
}

const formatDate = (dateString: string): string => {
  const date = new Date(dateString);
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

export default function SkillsList({
  skills,
  onEdit,
  onDelete,
  onToggleStatus,
  loading,
}: SkillsListProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50">
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Skill Name
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Description
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Status
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Version
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Updated
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {skills.map((skill) => (
            <tr key={skill.id} className="hover:bg-gray-50">
              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                {skill.skill_name}
              </td>
              <td className="px-6 py-4 text-sm text-gray-600">
                <div className="max-w-xs truncate">{skill.description || '—'}</div>
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <span
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    skill.is_active
                      ? 'bg-green-100 text-green-800'
                      : 'bg-gray-100 text-gray-800'
                  }`}
                >
                  {skill.is_active ? 'Active' : 'Inactive'}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                v{skill.version}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                {formatDate(skill.updated_at)}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                <button
                  onClick={() => onEdit(skill)}
                  disabled={loading}
                  className="text-blue-600 hover:text-blue-800 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Edit
                </button>
                <button
                  onClick={() => onToggleStatus(skill)}
                  disabled={loading}
                  className="text-amber-600 hover:text-amber-800 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {skill.is_active ? 'Deactivate' : 'Activate'}
                </button>
                <button
                  onClick={() => onDelete(skill)}
                  disabled={loading}
                  className="text-red-600 hover:text-red-800 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
