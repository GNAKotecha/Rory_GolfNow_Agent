import { useEffect, useRef } from 'react';
import { Skill } from '@/lib/api';

interface SkillSuggestionsProps {
  skills: Skill[];
  selectedIndex: number;
  onSelect: (skill: Skill) => void;
  onClose: () => void;
}

/**
 * Dropdown component for displaying slash command skill suggestions.
 *
 * Features:
 * - Keyboard navigation (arrow keys, enter, escape)
 * - Click selection
 * - Hover highlighting
 * - Auto-scroll selected item into view
 */
export function SkillSuggestions({
  skills,
  selectedIndex,
  onSelect,
  onClose,
}: SkillSuggestionsProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const selectedItemRef = useRef<HTMLButtonElement>(null);

  // Auto-scroll selected item into view
  useEffect(() => {
    if (selectedItemRef.current && containerRef.current) {
      const container = containerRef.current;
      const item = selectedItemRef.current;

      const containerRect = container.getBoundingClientRect();
      const itemRect = item.getBoundingClientRect();

      if (itemRect.bottom > containerRect.bottom) {
        item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      } else if (itemRect.top < containerRect.top) {
        item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  }, [selectedIndex]);

  if (skills.length === 0) {
    return (
      <div
        ref={containerRef}
        className="absolute bottom-full mb-2 w-full max-w-md bg-white border border-gray-200 rounded-lg shadow-lg"
      >
        <div className="p-4 text-center text-sm text-gray-500">
          No skills available. Contact an admin to create skills.
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="absolute bottom-full mb-2 w-full max-w-md bg-white border border-gray-200 rounded-lg shadow-lg max-h-64 overflow-y-auto"
    >
      <div className="p-2 border-b border-gray-100 flex items-center gap-2">
        <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
        <span className="text-xs font-medium text-gray-500">Available Skills</span>
        <button
          onClick={onClose}
          className="ml-auto text-gray-400 hover:text-gray-600 transition-colors"
          title="Close (ESC)"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="py-1">
        {skills.map((skill, index) => {
          const isSelected = index === selectedIndex;
          return (
            <button
              key={skill.id}
              ref={isSelected ? selectedItemRef : null}
              onClick={() => onSelect(skill)}
              className={`w-full text-left px-4 py-2.5 transition-colors ${
                isSelected
                  ? 'bg-gray-100 text-gray-900'
                  : 'text-gray-700 hover:bg-gray-50'
              }`}
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex-shrink-0">
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
                    <span className="text-white text-xs font-bold">
                      /{skill.skill_name.slice(0, 1).toUpperCase()}
                    </span>
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-medium text-gray-900">
                      /{skill.skill_name}
                    </span>
                    {!skill.is_active && (
                      <span className="text-xs text-gray-400">(inactive)</span>
                    )}
                  </div>
                  {skill.description && (
                    <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">
                      {skill.description}
                    </p>
                  )}
                </div>
                {isSelected && (
                  <div className="flex-shrink-0 text-gray-400">
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                      <path
                        fillRule="evenodd"
                        d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </div>
                )}
              </div>
            </button>
          );
        })}
      </div>

      <div className="p-2 border-t border-gray-100 text-xs text-gray-400">
        <div className="flex items-center justify-between px-2">
          <span>↑↓ Navigate</span>
          <span>↵ Select</span>
          <span>ESC Close</span>
        </div>
      </div>
    </div>
  );
}
