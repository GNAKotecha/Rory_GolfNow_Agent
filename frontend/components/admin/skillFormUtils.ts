/**
 * Shared utilities for skill form handling
 */

export interface SkillFormData {
  skill_name: string;
  description: string;
  skill_data: string;
}

export interface WorkflowStep {
  id: string;
  action: string;
}

/**
 * Reset form to initial state
 */
export function resetSkillForm(): SkillFormData {
  return {
    skill_name: '',
    description: '',
    skill_data: '{}',
  };
}

/**
 * Validate JSON and return success state
 */
export function validateSkillJSON(jsonString: string): {
  valid: boolean;
  error: string | null;
} {
  try {
    JSON.parse(jsonString);
    return { valid: true, error: null };
  } catch (e) {
    return {
      valid: false,
      error: e instanceof Error ? e.message : 'Invalid JSON',
    };
  }
}

/**
 * Convert workflow steps array to skill_data JSON string
 */
export function stepsToSkillData(steps: WorkflowStep[]): string {
  if (steps.length === 0) {
    return '{}';
  }

  const skillData = {
    workflow: {
      type: 'sequential',
      steps: steps.map((step, index) => ({
        id: `${index + 1}`,
        action: step.action.trim(),
      })),
    },
  };

  return JSON.stringify(skillData, null, 2);
}
