import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MoveCategoryModal from '../MoveCategoryModal';

describe('MoveCategoryModal', () => {
  it('renders nothing when not open', () => {
    const { container } = render(
      <MoveCategoryModal
        open={false}
        fromAddress="x@example.com"
        targetCategory="bulk"
        onCancel={() => {}}
        onConfirm={() => {}}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows the extracted domain in the apply-to-domain checkbox', () => {
    render(
      <MoveCategoryModal
        open
        fromAddress="newsletter@News.Example.COM"
        targetCategory="bulk"
        onCancel={() => {}}
        onConfirm={() => {}}
      />
    );
    // The checkbox label contains "Apply to entire" + a <strong> with the
    // lowercased domain. Find that <strong> specifically (the From: line
    // shows the original-cased address, so it won't collide).
    const label = screen.getByText(/Apply to entire/).closest('label');
    expect(label).toBeTruthy();
    expect(label.querySelector('strong')).toHaveTextContent('@news.example.com');
  });

  it('uses the target category in the title and confirm button', () => {
    render(
      <MoveCategoryModal
        open
        fromAddress="x@y.com"
        targetCategory="people"
        onCancel={() => {}}
        onConfirm={() => {}}
      />
    );
    expect(screen.getByRole('heading')).toHaveTextContent('Move to People');
    expect(screen.getByRole('button', { name: /Move to People/ })).toBeInTheDocument();
  });

  it('Cancel closes without calling onConfirm', async () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <MoveCategoryModal
        open
        fromAddress="x@y.com"
        targetCategory="bulk"
        onCancel={onCancel}
        onConfirm={onConfirm}
      />
    );
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('Confirm calls onConfirm with the checkbox state', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <MoveCategoryModal
        open
        fromAddress="newsletter@example.com"
        targetCategory="bulk"
        onCancel={() => {}}
        onConfirm={onConfirm}
      />
    );

    // Both unchecked by default.
    await user.click(screen.getByRole('button', { name: /Move to Bulk/ }));
    expect(onConfirm).toHaveBeenCalledWith({
      applyToDomain: false,
      applyToExisting: false,
    });
  });

  it('Confirm passes both checkboxes when checked', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <MoveCategoryModal
        open
        fromAddress="newsletter@example.com"
        targetCategory="bulk"
        onCancel={() => {}}
        onConfirm={onConfirm}
      />
    );

    const [domainCb, existingCb] = screen.getAllByRole('checkbox');
    await user.click(domainCb);
    await user.click(existingCb);
    await user.click(screen.getByRole('button', { name: /Move to Bulk/ }));

    expect(onConfirm).toHaveBeenCalledWith({
      applyToDomain: true,
      applyToExisting: true,
    });
  });

  it('shows an inline error and stays open when onConfirm rejects', async () => {
    const onConfirm = vi.fn().mockRejectedValue(new Error('Server said no'));
    const user = userEvent.setup();
    render(
      <MoveCategoryModal
        open
        fromAddress="x@y.com"
        targetCategory="bulk"
        onCancel={() => {}}
        onConfirm={onConfirm}
      />
    );
    await user.click(screen.getByRole('button', { name: /Move to Bulk/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Server said no');
    // Modal still mounted (heading still visible).
    expect(screen.getByRole('heading')).toHaveTextContent('Move to Bulk');
  });

  it('disables the apply-to-domain checkbox when from_address has no @', () => {
    render(
      <MoveCategoryModal
        open
        fromAddress="not-an-email"
        targetCategory="bulk"
        onCancel={() => {}}
        onConfirm={() => {}}
      />
    );
    const [domainCb] = screen.getAllByRole('checkbox');
    expect(domainCb).toBeDisabled();
  });
});
