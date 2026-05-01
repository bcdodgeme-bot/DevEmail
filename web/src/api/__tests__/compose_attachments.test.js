/**
 * Tests for the Phase 9 attachment helpers in api/compose.js. These mock
 * the global `fetch` so we can assert URL, method, and body shape.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let composeAPI;
let attachmentsAPI;
let fetchSpy;

beforeEach(async () => {
  vi.resetModules();
  fetchSpy = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({}),
  });
  globalThis.fetch = fetchSpy;
  ({ composeAPI, attachmentsAPI } = await import('../compose'));
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('composeAPI.sendWithAttachments', () => {
  it('POSTs multipart to /messages/compose with payload + file parts', async () => {
    const file = new File([new Uint8Array([1, 2, 3])], 'note.txt', { type: 'text/plain' });
    await composeAPI.sendWithAttachments({ account_id: 'a', subject: 'hi' }, [file]);

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, opts] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/messages/compose');
    expect(opts.method).toBe('POST');
    expect(opts.body).toBeInstanceOf(FormData);
    // Inspect FormData entries.
    const body = opts.body;
    const payloadStr = body.get('payload');
    expect(JSON.parse(payloadStr)).toEqual({ account_id: 'a', subject: 'hi' });
    const filesEntry = body.getAll('attachments');
    expect(filesEntry).toHaveLength(1);
    expect(filesEntry[0].name).toBe('note.txt');
  });

  it('does not set Content-Type — lets the browser add the multipart boundary', async () => {
    const file = new File(['x'], 'x.txt', { type: 'text/plain' });
    await composeAPI.sendWithAttachments({}, [file]);
    const [, opts] = fetchSpy.mock.calls[0];
    expect(opts.headers).toBeUndefined();
  });
});

describe('composeAPI.sendExistingDraft', () => {
  it('PATCH/POSTs JSON to /messages/compose with existing_message_id and is_draft=false', async () => {
    await composeAPI.sendExistingDraft({
      account_id: 'a',
      to_addresses: [{ address: 'x@y.com' }],
      existing_message_id: 'draft-1',
    });

    const [url, opts] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/messages/compose');
    expect(opts.method).toBe('POST');
    const body = JSON.parse(opts.body);
    expect(body.existing_message_id).toBe('draft-1');
    expect(body.is_draft).toBe(false);
  });
});

describe('attachmentsAPI', () => {
  it('getLimits hits /messages/config/attachments', async () => {
    await attachmentsAPI.getLimits();
    const [url] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/messages/config/attachments');
  });

  it('list hits /messages/{id}/attachments', async () => {
    await attachmentsAPI.list('msg-1');
    const [url] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/messages/msg-1/attachments');
  });

  it('upload POSTs multipart to /messages/{id}/attachments with files', async () => {
    const f1 = new File(['a'], 'a.txt', { type: 'text/plain' });
    const f2 = new File(['bb'], 'b.txt', { type: 'text/plain' });
    await attachmentsAPI.upload('msg-1', [f1, f2]);
    const [url, opts] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/messages/msg-1/attachments');
    expect(opts.method).toBe('POST');
    expect(opts.body).toBeInstanceOf(FormData);
    expect(opts.body.getAll('attachments')).toHaveLength(2);
  });

  it('delete hits DELETE /messages/{id}/attachments/{attId}', async () => {
    await attachmentsAPI.delete('msg-1', 'att-1');
    const [url, opts] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/messages/msg-1/attachments/att-1');
    expect(opts.method).toBe('DELETE');
  });

  it('downloadUrl returns the right path (sync — no fetch)', () => {
    const url = attachmentsAPI.downloadUrl('msg-1', 'att-1');
    expect(url).toBe('/api/messages/msg-1/attachments/att-1/download');
  });

  it('upload surfaces backend error detail', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 413,
      json: async () => ({ detail: 'too big' }),
    });
    const f = new File(['x'], 'x.txt', { type: 'text/plain' });
    await expect(attachmentsAPI.upload('msg-1', [f])).rejects.toThrow('too big');
  });
});
