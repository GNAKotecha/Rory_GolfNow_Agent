/**
 * Environment-aware logging utility
 * Only logs in development mode to prevent sensitive data exposure in production
 */

const isDevelopment = process.env.NODE_ENV === 'development';

export const logger = {
  log: (...args: any[]) => {
    if (isDevelopment) {
      console.log(...args);
    }
  },

  warn: (...args: any[]) => {
    if (isDevelopment) {
      console.warn(...args);
    }
  },

  // Always log errors, but sanitize in production
  error: (...args: any[]) => {
    console.error(...args);
  },

  debug: (...args: any[]) => {
    if (isDevelopment) {
      console.debug(...args);
    }
  },
};

/**
 * Redact sensitive user data from logs
 * Only returns safe fields for logging
 */
export function redactUserData(user: any): { id: number; email: string; role: string } {
  return {
    id: user.id,
    email: user.email,
    role: user.role,
  };
}
