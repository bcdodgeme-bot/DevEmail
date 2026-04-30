import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// Auto-unmount React trees between tests so leftover portals/listeners
// don't leak across cases.
afterEach(() => {
  cleanup();
});
