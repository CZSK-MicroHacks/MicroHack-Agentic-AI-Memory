/**
 * Mock Authentication Module
 *
 * Provides a hardcoded current user and an auth-header helper that is
 * injected into every backend request.
 *
 * Migration to Azure Entra ID:
 *   Replace `getCurrentUser()` with MSAL.js `acquireTokenSilent()`.
 *   Replace `getAuthHeaders()` to return `{ Authorization: 'Bearer <token>' }`.
 *   The rest of the app stays unchanged.
 */

export interface User {
  user_id: string;
  display_name: string;
  email: string;
  avatar_url: string | null;
  initials: string;
}

/**
 * The locally-mocked current user.
 * Change the `user_id` here to simulate logging in as a different user.
 */
const CURRENT_USER_ID = 'user-alice';
// const CURRENT_USER_ID = 'user-bob';

/**
 * Returns headers that identify the current user to the backend.
 */
export function getAuthHeaders(): Record<string, string> {
  return { 'X-User-ID': CURRENT_USER_ID };
}
