import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CategoryPills from '../CategoryPills';

const COUNTS = {
  all:    { unread: 12, total: 200 },
  people: { unread: 8,  total: 60  },
  bulk:   { unread: 4,  total: 140 },
};

describe('CategoryPills', () => {
  it('renders three buttons with their unread counts', () => {
    render(<CategoryPills activeCategory="all" counts={COUNTS} onChange={() => {}} />);

    expect(screen.getByRole('tab', { name: /All/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /People/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Bulk/ })).toBeInTheDocument();

    expect(screen.getByTestId('pill-count-all')).toHaveTextContent('12');
    expect(screen.getByTestId('pill-count-people')).toHaveTextContent('8');
    expect(screen.getByTestId('pill-count-bulk')).toHaveTextContent('4');
  });

  it('marks the active pill via aria-selected based on activeCategory prop', () => {
    const { rerender } = render(
      <CategoryPills activeCategory="all" counts={COUNTS} onChange={() => {}} />
    );
    expect(screen.getByRole('tab', { name: /All/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: /Bulk/ })).toHaveAttribute('aria-selected', 'false');

    rerender(<CategoryPills activeCategory="bulk" counts={COUNTS} onChange={() => {}} />);
    expect(screen.getByRole('tab', { name: /Bulk/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: /All/ })).toHaveAttribute('aria-selected', 'false');
  });

  it('treats null activeCategory as All (the URL "no param" case)', () => {
    render(<CategoryPills activeCategory={null} counts={COUNTS} onChange={() => {}} />);
    expect(screen.getByRole('tab', { name: /All/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('calls onChange with the clicked pill key', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<CategoryPills activeCategory="all" counts={COUNTS} onChange={onChange} />);

    await user.click(screen.getByRole('tab', { name: /Bulk/ }));
    expect(onChange).toHaveBeenCalledWith('bulk');
  });

  it('exposes "X unread · Y total" tooltip via title attribute', () => {
    render(<CategoryPills activeCategory="all" counts={COUNTS} onChange={() => {}} />);
    expect(screen.getByRole('tab', { name: /People/ })).toHaveAttribute(
      'title', '8 unread · 60 total',
    );
  });

  it('dims (does not hide) zero-unread counts', () => {
    const zero = {
      all:    { unread: 0, total: 5 },
      people: { unread: 0, total: 3 },
      bulk:   { unread: 0, total: 2 },
    };
    render(<CategoryPills activeCategory="all" counts={zero} onChange={() => {}} />);
    const peopleCount = screen.getByTestId('pill-count-people');
    // Class names from CSS modules get hashed — check via class includes "Zero".
    expect(peopleCount.className).toMatch(/Zero/);
    expect(peopleCount).toHaveTextContent('0');
  });

  it('safely defaults missing count slots to zero', () => {
    render(<CategoryPills activeCategory="all" counts={undefined} onChange={() => {}} />);
    expect(screen.getByTestId('pill-count-all')).toHaveTextContent('0');
    expect(screen.getByTestId('pill-count-people')).toHaveTextContent('0');
    expect(screen.getByTestId('pill-count-bulk')).toHaveTextContent('0');
  });
});
