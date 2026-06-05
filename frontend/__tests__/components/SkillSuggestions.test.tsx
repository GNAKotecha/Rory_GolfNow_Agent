import { render, screen, fireEvent } from '@testing-library/react';
import { SkillSuggestions } from '@/components/SkillSuggestions';
import { Skill } from '@/lib/api';

const mockSkills: Skill[] = [
  {
    id: 1,
    tenant_id: 1,
    skill_name: 'onboarding',
    description: 'Onboard new users',
    skill_data: {},
    version: 1,
    is_active: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    created_by: 1,
  },
  {
    id: 2,
    tenant_id: 1,
    skill_name: 'report_generator',
    description: 'Generate reports',
    skill_data: {},
    version: 1,
    is_active: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    created_by: 1,
  },
  {
    id: 3,
    tenant_id: 1,
    skill_name: 'data_export',
    description: null,
    skill_data: {},
    version: 1,
    is_active: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    created_by: 1,
  },
];

describe('SkillSuggestions', () => {
  const mockOnSelect = jest.fn();
  const mockOnClose = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should render skills list', () => {
    render(
      <SkillSuggestions
        skills={mockSkills}
        selectedIndex={0}
        onSelect={mockOnSelect}
        onClose={mockOnClose}
      />
    );

    expect(screen.getByText('/onboarding')).toBeInTheDocument();
    expect(screen.getByText('/report_generator')).toBeInTheDocument();
    expect(screen.getByText('/data_export')).toBeInTheDocument();
  });

  it('should display skill descriptions', () => {
    render(
      <SkillSuggestions
        skills={mockSkills}
        selectedIndex={0}
        onSelect={mockOnSelect}
        onClose={mockOnClose}
      />
    );

    expect(screen.getByText('Onboard new users')).toBeInTheDocument();
    expect(screen.getByText('Generate reports')).toBeInTheDocument();
  });

  it('should mark inactive skills', () => {
    render(
      <SkillSuggestions
        skills={mockSkills}
        selectedIndex={2}
        onSelect={mockOnSelect}
        onClose={mockOnClose}
      />
    );

    expect(screen.getByText('(inactive)')).toBeInTheDocument();
  });

  it('should highlight selected skill', () => {
    const { rerender } = render(
      <SkillSuggestions
        skills={mockSkills}
        selectedIndex={0}
        onSelect={mockOnSelect}
        onClose={mockOnClose}
      />
    );

    const firstSkillButton = screen.getByText('/onboarding').closest('button');
    expect(firstSkillButton).toHaveClass('bg-gray-100');

    rerender(
      <SkillSuggestions
        skills={mockSkills}
        selectedIndex={1}
        onSelect={mockOnSelect}
        onClose={mockOnClose}
      />
    );

    const secondSkillButton = screen.getByText('/report_generator').closest('button');
    expect(secondSkillButton).toHaveClass('bg-gray-100');
  });

  it('should call onSelect when skill is clicked', () => {
    render(
      <SkillSuggestions
        skills={mockSkills}
        selectedIndex={0}
        onSelect={mockOnSelect}
        onClose={mockOnClose}
      />
    );

    const skillButton = screen.getByText('/onboarding').closest('button');
    fireEvent.click(skillButton!);

    expect(mockOnSelect).toHaveBeenCalledWith(mockSkills[0]);
  });

  it('should call onClose when close button is clicked', () => {
    render(
      <SkillSuggestions
        skills={mockSkills}
        selectedIndex={0}
        onSelect={mockOnSelect}
        onClose={mockOnClose}
      />
    );

    const closeButton = screen.getByTitle('Close (ESC)');
    fireEvent.click(closeButton);

    expect(mockOnClose).toHaveBeenCalled();
  });

  it('should show empty state when no skills available', () => {
    render(
      <SkillSuggestions
        skills={[]}
        selectedIndex={0}
        onSelect={mockOnSelect}
        onClose={mockOnClose}
      />
    );

    expect(screen.getByText(/No skills available/)).toBeInTheDocument();
  });

  it('should display keyboard navigation hints', () => {
    render(
      <SkillSuggestions
        skills={mockSkills}
        selectedIndex={0}
        onSelect={mockOnSelect}
        onClose={mockOnClose}
      />
    );

    expect(screen.getByText('↑↓ Navigate')).toBeInTheDocument();
    expect(screen.getByText('↵ Select')).toBeInTheDocument();
    expect(screen.getByText('ESC Close')).toBeInTheDocument();
  });
});
