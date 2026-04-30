import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ContextMenu from '../ContextMenu';

describe('ContextMenu', () => {
  it('renders nothing when anchor is null', () => {
    const { container } = render(
      <ContextMenu anchor={null} items={[]} onClose={() => {}} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders item labels at the cursor position', () => {
    render(
      <ContextMenu
        anchor={{ x: 100, y: 200 }}
        items={[{ label: 'Move to Bulk', onClick: () => {} }]}
        onClose={() => {}}
      />
    );
    expect(screen.getByRole('menuitem', { name: 'Move to Bulk' })).toBeInTheDocument();
  });

  it('clicking an item calls its handler and closes', async () => {
    const onClose = vi.fn();
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(
      <ContextMenu
        anchor={{ x: 10, y: 10 }}
        items={[{ label: 'Action', onClick }]}
        onClose={onClose}
      />
    );
    await user.click(screen.getByRole('menuitem', { name: 'Action' }));
    expect(onClose).toHaveBeenCalled();
    expect(onClick).toHaveBeenCalled();
  });

  it('Escape closes the menu', () => {
    const onClose = vi.fn();
    render(
      <ContextMenu
        anchor={{ x: 10, y: 10 }}
        items={[{ label: 'A', onClick: () => {} }]}
        onClose={onClose}
      />
    );
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('scroll closes the menu', () => {
    const onClose = vi.fn();
    render(
      <ContextMenu
        anchor={{ x: 10, y: 10 }}
        items={[{ label: 'A', onClick: () => {} }]}
        onClose={onClose}
      />
    );
    fireEvent.scroll(window);
    expect(onClose).toHaveBeenCalled();
  });
});
