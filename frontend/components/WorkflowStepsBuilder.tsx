'use client';

import { useState } from 'react';

export interface WorkflowStep {
  id: string;
  action: string;
}

interface WorkflowStepsBuilderProps {
  steps: WorkflowStep[];
  onStepsChange: (steps: WorkflowStep[]) => void;
}

export default function WorkflowStepsBuilder({
  steps,
  onStepsChange,
}: WorkflowStepsBuilderProps) {
  const [nextId, setNextId] = useState(steps.length > 0 ? steps.length : 0);

  const generateId = () => {
    const newId = nextId + 1;
    setNextId(newId);
    return `step-${newId}`;
  };

  const handleAddStep = () => {
    const newStep: WorkflowStep = {
      id: generateId(),
      action: '',
    };
    onStepsChange([...steps, newStep]);
  };

  const handleUpdateStep = (id: string, action: string) => {
    onStepsChange(
      steps.map((step) => (step.id === id ? { ...step, action: action.trim() } : step))
    );
  };

  const handleRemoveStep = (id: string) => {
    onStepsChange(steps.filter((step) => step.id !== id));
  };

  const handleMoveStep = (id: string, direction: 'up' | 'down') => {
    const index = steps.findIndex((step) => step.id === id);
    if (index === -1) return;

    if (direction === 'up' && index > 0) {
      const newSteps = [...steps];
      [newSteps[index], newSteps[index - 1]] = [newSteps[index - 1], newSteps[index]];
      onStepsChange(newSteps);
    } else if (direction === 'down' && index < steps.length - 1) {
      const newSteps = [...steps];
      [newSteps[index], newSteps[index + 1]] = [newSteps[index + 1], newSteps[index]];
      onStepsChange(newSteps);
    }
  };

  const handleValidationOnSubmit = (): { valid: boolean; error: string | null } => {
    const emptySteps = steps.filter((step) => !step.action.trim());
    if (emptySteps.length > 0) {
      return {
        valid: false,
        error: 'All steps must have an action',
      };
    }
    return { valid: true, error: null };
  };

  // Export validation function to parent
  (handleValidationOnSubmit as any).validate = handleValidationOnSubmit;

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <label className="block text-sm font-medium text-gray-700">
          Workflow Steps (Optional)
        </label>
        <span className="text-xs text-gray-500">{steps.length} step(s)</span>
      </div>

      {/* Steps List */}
      <div className="space-y-2">
        {steps.length === 0 ? (
          <div className="text-center py-4 text-sm text-gray-500 bg-gray-50 rounded border border-gray-200">
            No steps added yet. Click "Add Step" to create one.
          </div>
        ) : (
          steps.map((step, index) => (
            <div
              key={step.id}
              className="flex items-center gap-2 p-3 bg-gray-50 rounded border border-gray-200"
            >
              {/* Step Number */}
              <div className="flex-shrink-0 w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center text-sm font-medium text-gray-700">
                {index + 1}
              </div>

              {/* Action Input */}
              <input
                type="text"
                value={step.action}
                onChange={(e) => handleUpdateStep(step.id, e.target.value)}
                placeholder="Enter action (e.g., validate email, send notification)"
                className="flex-grow px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              />

              {/* Move Up Button */}
              <button
                type="button"
                onClick={() => handleMoveStep(step.id, 'up')}
                disabled={index === 0}
                className="flex-shrink-0 px-2 py-1 text-sm font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-200 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                title="Move up"
              >
                ↑
              </button>

              {/* Move Down Button */}
              <button
                type="button"
                onClick={() => handleMoveStep(step.id, 'down')}
                disabled={index === steps.length - 1}
                className="flex-shrink-0 px-2 py-1 text-sm font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-200 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                title="Move down"
              >
                ↓
              </button>

              {/* Remove Button */}
              <button
                type="button"
                onClick={() => handleRemoveStep(step.id)}
                className="flex-shrink-0 px-2 py-1 text-sm font-medium text-red-600 hover:text-red-800 hover:bg-red-50 rounded"
                title="Delete step"
              >
                ✕
              </button>
            </div>
          ))
        )}
      </div>

      {/* Add Step Button */}
      <button
        type="button"
        onClick={handleAddStep}
        className="w-full px-3 py-2 text-sm font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-md hover:bg-blue-100"
      >
        + Add Step
      </button>

      <p className="text-xs text-gray-500">
        Workflow steps are optional. You can create a skill without any steps.
      </p>
    </div>
  );
}
