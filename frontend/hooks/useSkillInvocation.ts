import { useState, useCallback } from 'react';
import { apiClient, Skill } from '@/lib/api';

interface InvokeSkillRequest {
  skill_name: string;
  context: Record<string, any>;
}

interface InvokeSkillResponse {
  success: boolean;
  skill_name: string;
  message: string;
  context: Record<string, any>;
}

interface UseSkillInvocationReturn {
  skills: Skill[];
  loading: boolean;
  error: string | null;
  fetchSkills: () => Promise<void>;
  invokeSkill: (skillName: string, context?: Record<string, any>) => Promise<InvokeSkillResponse>;
  matchSkill: (userMessage: string) => Promise<Skill | null>;
}

/**
 * Hook for managing skill invocation in the chat interface.
 *
 * Features:
 * - Fetch available skills from API
 * - Invoke a skill by name
 * - Match user message to skills using intent patterns
 */
export function useSkillInvocation(): UseSkillInvocationReturn {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Fetch all available skills for the current user's tenant.
   * Only fetches active skills.
   */
  const fetchSkills = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.getSkills(undefined, undefined, true); // activeOnly=true
      setSkills(response.skills);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch skills';
      setError(errorMessage);
      console.error('Failed to fetch skills:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Invoke a skill by name with optional context.
   *
   * @param skillName - Name of the skill to invoke
   * @param context - Optional context data for skill execution
   * @returns Skill execution result
   */
  const invokeSkill = useCallback(async (
    skillName: string,
    context: Record<string, any> = {}
  ): Promise<InvokeSkillResponse> => {
    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.invokeSkill(skillName, context);
      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to invoke skill';
      setError(errorMessage);
      console.error('Failed to invoke skill:', err);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Match a user message against skill intent patterns.
   *
   * @param userMessage - User's input message
   * @returns Matched skill or null if no match found
   */
  const matchSkill = useCallback(async (userMessage: string): Promise<Skill | null> => {
    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.matchSkill(userMessage);
      return response.matched ? response.skill : null;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to match skill';
      setError(errorMessage);
      console.error('Failed to match skill:', err);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    skills,
    loading,
    error,
    fetchSkills,
    invokeSkill,
    matchSkill,
  };
}
