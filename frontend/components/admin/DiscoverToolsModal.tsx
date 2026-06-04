'use client';

import { useState, useEffect } from 'react';
import { TenantMCPIntegration, MCPToolSchema, apiClient } from '@/lib/api';

interface DiscoverToolsModalProps {
  isOpen: boolean;
  connection: TenantMCPIntegration | null;
  onClose: () => void;
}

export default function DiscoverToolsModal({
  isOpen,
  connection,
  onClose,
}: DiscoverToolsModalProps) {
  const [tools, setTools] = useState<MCPToolSchema[]>([]);
  const [selectedTool, setSelectedTool] = useState<MCPToolSchema | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && connection) {
      setLoading(true);
      setError(null);

      const discoverTools = async () => {
        try {
          // List all available tools; backend should enhance to filter by connection
          const allTools = await apiClient.listAvailableTools();

          if (connection.is_enabled) {
            setTools(allTools);
          } else {
            setError('Connection is disabled. Enable it to discover tools.');
          }
        } catch (err) {
          setError(
            err instanceof Error
              ? err.message
              : 'Failed to discover tools for this connection'
          );
          setTools([]);
        } finally {
          setLoading(false);
        }
      };

      discoverTools();
    }
  }, [isOpen, connection]);

  if (!isOpen || !connection) return null;

  const handleToolClick = (tool: MCPToolSchema) => {
    setSelectedTool(selectedTool?.name === tool.name ? null : tool);
  };

  const handleClose = () => {
    setTools([]);
    setSelectedTool(null);
    setError(null);
    onClose();
  };

  const formatJSON = (obj: any): string => {
    return JSON.stringify(obj, null, 2);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-lg max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex-shrink-0">
          <h2 className="text-lg font-semibold text-gray-900">Available Tools</h2>
          <p className="text-sm text-gray-600 mt-1">{connection.integration_name}</p>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div className="text-center py-12">
              <div className="inline-block">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              </div>
              <p className="text-sm text-gray-600 mt-4">Discovering tools...</p>
            </div>
          ) : error ? (
            <div className="p-4 bg-red-50 border border-red-200 rounded-md">
              <h3 className="text-sm font-semibold text-red-800 mb-1">Error</h3>
              <p className="text-sm text-red-700">{error}</p>
            </div>
          ) : tools.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-sm text-gray-500">No tools available for this connection</p>
            </div>
          ) : (
            <div className="space-y-3">
              {tools.map((tool) => (
                <div key={tool.name}>
                  {/* Tool Summary */}
                  <button
                    onClick={() => handleToolClick(tool)}
                    className="w-full text-left p-3 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="text-sm font-medium text-gray-900">{tool.name}</h3>
                        <p className="text-xs text-gray-600 mt-1">{tool.description}</p>
                      </div>
                      <span className="text-gray-400">
                        {selectedTool?.name === tool.name ? '▼' : '▶'}
                      </span>
                    </div>
                  </button>

                  {/* Tool Details */}
                  {selectedTool?.name === tool.name && (
                    <div className="mt-2 p-3 bg-gray-50 border border-gray-200 rounded-md">
                      <h4 className="text-xs font-semibold text-gray-700 mb-2">Input Schema</h4>
                      <pre className="text-xs bg-white border border-gray-300 rounded p-2 overflow-x-auto max-h-48 overflow-y-auto">
                        {formatJSON(tool.inputSchema)}
                      </pre>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200 flex-shrink-0">
          <div className="text-xs text-gray-600 mb-3">
            {tools.length > 0 && (
              <p>Total tools available: <span className="font-semibold">{tools.length}</span></p>
            )}
          </div>
          <button
            onClick={handleClose}
            className="w-full px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
