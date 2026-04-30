import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let setMessageCategory;

describe('classification API: setMessageCategory', () => {
  let fetchSpy;

  beforeEach(async () => {
    // Reset module state so each test gets a fresh fetch spy.
    vi.resetModules();
    fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'msg-1', category: 'bulk', category_source: 'override' }),
    });
    globalThis.fetch = fetchSpy;
    ({ setMessageCategory } = await import('../classification'));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('POSTs to /api/messages/{id}/category with the right body shape', async () => {
    await setMessageCategory('msg-1', {
      category: 'bulk',
      applyToDomain: true,
      applyToExisting: false,
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, opts] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/messages/msg-1/category');
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body)).toEqual({
      category: 'bulk',
      apply_to_domain: true,
      apply_to_existing: false,
    });
  });

  it('defaults apply_to_* to false when not provided', async () => {
    await setMessageCategory('msg-1', { category: 'people' });

    const [, opts] = fetchSpy.mock.calls[0];
    expect(JSON.parse(opts.body)).toEqual({
      category: 'people',
      apply_to_domain: false,
      apply_to_existing: false,
    });
  });
});
