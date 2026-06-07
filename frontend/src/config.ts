const configuredApiUrl = import.meta.env.VITE_API_URL?.replace(/\/+$/, '');

export const API_BASE_URL = configuredApiUrl
  ? `${configuredApiUrl}/api`
  : '/api';

export const REQUEST_TIMEOUT_MS = 30_000;
export const UPLOAD_TIMEOUT_MS = 120_000;
export const UPLOAD_MAX_FILES = 10;
export const UPLOAD_MAX_FILE_BYTES = 10 * 1024 * 1024;
export const UPLOAD_MAX_TOTAL_BYTES = 50 * 1024 * 1024;
