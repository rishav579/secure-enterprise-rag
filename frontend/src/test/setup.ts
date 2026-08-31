import '@testing-library/jest-dom';

// Mock crypto.randomUUID for jsdom if needed
if (!globalThis.crypto) {
  // @ts-ignore
  globalThis.crypto = {};
}
if (!globalThis.crypto.randomUUID) {
  globalThis.crypto.randomUUID = () => '11111111-2222-3333-4444-555555555555';
}
