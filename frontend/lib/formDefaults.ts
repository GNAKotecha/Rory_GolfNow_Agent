import { TenantMCPIntegrationCreate } from './api';

export const getMCPFormDefaults = (): TenantMCPIntegrationCreate => ({
  integration_name: '',
  auth_type: 'oauth',
  config: {},
});
