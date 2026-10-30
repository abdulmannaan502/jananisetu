// Hardened session token storage: uses in-memory token + HttpOnly cookie (never persisted in localStorage)
let inMemoryToken: string | null = null;

export function getStoredToken(): string | null {
  return inMemoryToken;
}

export function setStoredToken(token: string | null): void {
  inMemoryToken = token;
  try {
    localStorage.removeItem('jananisetu_jwt_token');
  } catch {
    // ignore
  }
}

export async function apiRequest<T>(
  path: string,
  method: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE' = 'GET',
  body?: unknown
): Promise<T> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    'X-Requested-With': 'XMLHttpRequest',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const options: RequestInit = {
    method,
    headers,
    credentials: 'include',
  };

  if (body instanceof FormData) {
    options.body = body;
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }

  const response = await fetch(path, options);
  const text = await response.text();
  let parsed: any = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = text;
  }

  if (!response.ok) {
    const message =
      (parsed && typeof parsed === 'object' && parsed.detail) ||
      (typeof parsed === 'string' && parsed) ||
      `HTTP ${response.status}`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }

  return parsed as T;
}
