/**
 * Authentication module.
 *
 * Modes:
 * - `mock`  (local development): sends `X-Mock-User-ID`
 * - `entra` (production/staging): sends `Authorization: Bearer <token>`
 */

import {
  PublicClientApplication,
  type AuthenticationResult,
  type AccountInfo,
} from '@azure/msal-browser';

export interface User {
  user_id: string;
  display_name: string;
  email: string;
  avatar_url: string | null;
  initials: string;
}

type AuthMode = 'mock' | 'entra';

type RuntimeAuthConfig = {
  authMode?: AuthMode;
  entraTenantId?: string;
  entraClientId?: string;
  entraApiScope?: string;
};

const MOCK_USER_STORAGE_KEY = 'mockUserId';
const DEFAULT_MOCK_USER_ID = 'user-alice';
const runtimeConfig: RuntimeAuthConfig = (window as any).__APP_CONFIG__ ?? {};

let msalApp: PublicClientApplication | null = null;
let msalInitPromise: Promise<void> | null = null;

function getAuthMode(): AuthMode {
  const runtimeMode = runtimeConfig.authMode;
  if (runtimeMode === 'entra' || runtimeMode === 'mock') {
    return runtimeMode;
  }

  const envMode = (import.meta.env.AUTH_MODE ?? import.meta.env.VITE_AUTH_MODE ?? '').toString().trim().toLowerCase();
  return envMode === 'entra' ? 'entra' : 'mock';
}

function getMockUserId(): string {
  const urlUser = new URLSearchParams(window.location.search).get('mockUser')?.trim();
  if (urlUser) {
    localStorage.setItem(MOCK_USER_STORAGE_KEY, urlUser);
    return urlUser;
  }
  const fromStorage = localStorage.getItem(MOCK_USER_STORAGE_KEY)?.trim();
  return fromStorage || DEFAULT_MOCK_USER_ID;
}

export function setMockUserId(userId: string): void {
  localStorage.setItem(MOCK_USER_STORAGE_KEY, userId);
}

export function getCurrentMockUserId(): string {
  return getMockUserId();
}

export function isMockAuthMode(): boolean {
  return getAuthMode() === 'mock';
}

function getMsalConfig() {
  const tenantId = runtimeConfig.entraTenantId?.trim();
  const clientId = runtimeConfig.entraClientId?.trim();
  if (!tenantId || !clientId) {
    throw new Error('Missing Entra configuration (entraTenantId/entraClientId)');
  }

  return {
    auth: {
      clientId,
      authority: `https://login.microsoftonline.com/${tenantId}`,
    },
    cache: {
      cacheLocation: 'sessionStorage' as const,
    },
  };
}

function getApiScope(): string {
  const scope = runtimeConfig.entraApiScope?.trim();
  if (!scope) {
    throw new Error('Missing Entra API scope (entraApiScope)');
  }
  return scope;
}

async function ensureMsalInitialized(): Promise<PublicClientApplication> {
  if (!msalApp) {
    msalApp = new PublicClientApplication(getMsalConfig());
  }
  if (!msalInitPromise) {
    msalInitPromise = (async () => {
      await msalApp!.initialize();
      const redirectResult = await msalApp!.handleRedirectPromise();
      if (redirectResult?.account) {
        msalApp!.setActiveAccount(redirectResult.account);
      }
    })();
  }
  await msalInitPromise;
  return msalApp;
}

async function acquireApiToken(): Promise<string> {
  const scope = getApiScope();
  const app = await ensureMsalInitialized();

  const active = app.getActiveAccount() ?? app.getAllAccounts()[0] ?? null;
  if (active) {
    app.setActiveAccount(active);
  }

  let account: AccountInfo | null = app.getActiveAccount();
  if (!account) {
    const loginResult = await app.loginPopup({ scopes: [scope] });
    account = loginResult.account;
    if (account) {
      app.setActiveAccount(account);
    }
  }

  if (!account) {
    throw new Error('Unable to determine authenticated account');
  }

  try {
    const silentResult: AuthenticationResult = await app.acquireTokenSilent({
      account,
      scopes: [scope],
    });
    return silentResult.accessToken;
  } catch {
    const interactiveResult = await app.acquireTokenPopup({ scopes: [scope] });
    return interactiveResult.accessToken;
  }
}

/**
 * Returns authentication headers for backend requests.
 */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  if (getAuthMode() === 'mock') {
    return { 'X-Mock-User-ID': getMockUserId() };
  }

  const token = await acquireApiToken();
  return { Authorization: `Bearer ${token}` };
}
