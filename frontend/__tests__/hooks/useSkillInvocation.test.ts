import { renderHook, waitFor } from '@testing-library/react';
import { useSkillInvocation } from '@/hooks/useSkillInvocation';
import { apiClient } from '@/lib/api';

// Mock the apiClient
jest.mock('@/lib/api', () => ({
  apiClient: {
    getSkills: jest.fn(),
    invokeSkill: jest.fn(),
    matchSkill: jest.fn(),
  },
}));

describe('useSkillInvocation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('fetchSkills', () => {
    it('should fetch skills successfully', async () => {
      const mockSkills = [
        {
          id: 1,
          tenant_id: 1,
          skill_name: 'test_skill',
          description: 'Test skill',
          skill_data: {},
          version: 1,
          is_active: true,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
          created_by: 1,
        },
      ];

      (apiClient.getSkills as jest.Mock).mockResolvedValue({
        skills: mockSkills,
        total: 1,
      });

      const { result } = renderHook(() => useSkillInvocation());

      expect(result.current.skills).toEqual([]);
      expect(result.current.loading).toBe(false);

      await waitFor(async () => {
        await result.current.fetchSkills();
      });

      await waitFor(() => {
        expect(result.current.skills).toEqual(mockSkills);
      });

      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
      expect(apiClient.getSkills).toHaveBeenCalledWith(undefined, undefined, true);
    });

    it('should handle fetch error', async () => {
      const errorMessage = 'Failed to fetch skills';
      (apiClient.getSkills as jest.Mock).mockRejectedValue(new Error(errorMessage));

      const { result } = renderHook(() => useSkillInvocation());

      await waitFor(async () => {
        await result.current.fetchSkills();
      });

      await waitFor(() => {
        expect(result.current.error).toBe(errorMessage);
      });

      expect(result.current.skills).toEqual([]);
      expect(result.current.loading).toBe(false);
    });
  });

  describe('invokeSkill', () => {
    it('should invoke skill successfully', async () => {
      const mockResponse = {
        success: true,
        skill_name: 'test_skill',
        message: 'Skill executed successfully',
        context: { result: 'success' },
      };

      (apiClient.invokeSkill as jest.Mock).mockResolvedValue(mockResponse);

      const { result } = renderHook(() => useSkillInvocation());

      let response;
      await waitFor(async () => {
        response = await result.current.invokeSkill('test_skill', { foo: 'bar' });
      });

      expect(response).toEqual(mockResponse);
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
      expect(apiClient.invokeSkill).toHaveBeenCalledWith('test_skill', { foo: 'bar' });
    });

    it('should handle invocation error', async () => {
      const errorMessage = 'Skill not found';
      (apiClient.invokeSkill as jest.Mock).mockRejectedValue(new Error(errorMessage));

      const { result } = renderHook(() => useSkillInvocation());

      await expect(async () => {
        await result.current.invokeSkill('nonexistent_skill');
      }).rejects.toThrow();

      await waitFor(() => {
        expect(result.current.error).toBe(errorMessage);
      });

      expect(result.current.loading).toBe(false);
    });
  });

  describe('matchSkill', () => {
    it('should match skill successfully', async () => {
      const mockSkill = {
        id: 1,
        tenant_id: 1,
        skill_name: 'test_skill',
        description: 'Test skill',
        skill_data: {},
        version: 1,
        is_active: true,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
        created_by: 1,
      };

      (apiClient.matchSkill as jest.Mock).mockResolvedValue({
        matched: true,
        skill: mockSkill,
      });

      const { result } = renderHook(() => useSkillInvocation());

      let matchedSkill;
      await waitFor(async () => {
        matchedSkill = await result.current.matchSkill('test message');
      });

      expect(matchedSkill).toEqual(mockSkill);
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
      expect(apiClient.matchSkill).toHaveBeenCalledWith('test message');
    });

    it('should return null when no match found', async () => {
      (apiClient.matchSkill as jest.Mock).mockResolvedValue({
        matched: false,
        skill: null,
      });

      const { result } = renderHook(() => useSkillInvocation());

      let matchedSkill;
      await waitFor(async () => {
        matchedSkill = await result.current.matchSkill('unmatched message');
      });

      expect(matchedSkill).toBeNull();
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it('should handle match error', async () => {
      const errorMessage = 'Match failed';
      (apiClient.matchSkill as jest.Mock).mockRejectedValue(new Error(errorMessage));

      const { result } = renderHook(() => useSkillInvocation());

      let matchedSkill;
      await waitFor(async () => {
        matchedSkill = await result.current.matchSkill('test message');
      });

      expect(matchedSkill).toBeNull();
      expect(result.current.error).toBe(errorMessage);
      expect(result.current.loading).toBe(false);
    });
  });
});
