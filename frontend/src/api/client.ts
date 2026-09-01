export class APIError extends Error {
  status: number;
  data: any;

  constructor(status: number, message: string, data?: any) {
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.data = data;
  }
}

// Token storage abstraction
// Explicit MVP Trade-off: Tokens are stored in memory and mirrored to sessionStorage
// to support page refresh within the same tab. It is accessible to JS and not XSS-proof.
let inMemoryToken: string | null = sessionStorage.getItem('rag_token');

export const setAuthToken = (token: string | null) => {
  inMemoryToken = token;
  if (token) {
    sessionStorage.setItem('rag_token', token);
  } else {
    sessionStorage.removeItem('rag_token');
  }
};

export const getAuthToken = (): string | null => {
  return inMemoryToken;
};

export async function apiClient<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {});

  // Set Authorization header if token is available
  const token = getAuthToken();
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  // Set default JSON Content-Type unless uploading FormData
  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const url = endpoint.startsWith('http') ? endpoint : `/api/v1${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

  const response = await fetch(url, {
    ...options,
    headers,
  });

  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  let data: any;
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    let errorMessage = '';
    if (typeof data === 'object' && data !== null) {
      if (typeof data.detail === 'string') {
        errorMessage = data.detail;
      } else if (typeof data.detail === 'object' && data.detail !== null) {
        if (typeof data.detail.message === 'string') {
          errorMessage = data.detail.message;
        } else {
          errorMessage = JSON.stringify(data.detail);
        }
      } else if (Array.isArray(data.detail)) {
        // Pydantic validation errors
        errorMessage = data.detail.map((err: any) => err.msg || JSON.stringify(err)).join(', ');
      } else if (typeof data.message === 'string') {
        errorMessage = data.message;
      }
    } else if (typeof data === 'string' && data.trim()) {
      errorMessage = data;
    }

    // Normalized fallback status messages if no specific error was extracted
    if (!errorMessage) {
      if (response.status === 401) {
        errorMessage = 'Invalid or expired session. Please log in again.';
      } else if (response.status === 403) {
        errorMessage = 'You do not have permission to access this resource.';
      } else if (response.status === 404) {
        errorMessage = 'The requested resource was not found.';
      } else if (response.status === 409) {
        errorMessage = 'A conflict occurred with an existing resource.';
      } else if (response.status === 502 || response.status === 504) {
        errorMessage = 'Upstream service is temporarily unavailable.';
      } else {
        errorMessage = 'An unexpected error occurred.';
      }
    }

    if (response.status === 401) {
      setAuthToken(null);
    }

    throw new APIError(response.status, errorMessage, data);
  }

  return data as T;
}
