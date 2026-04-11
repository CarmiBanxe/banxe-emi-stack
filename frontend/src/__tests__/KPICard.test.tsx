/**
 * KPICard Tests — tabular-nums, delta display, sparkline
 * IL-ADDS-01
 */
import { render, screen } from '@testing-library/react'
import { describe, test, expect } from 'vitest'
import { KPICard } from '../components/ui/KPICard'

describe('KPICard', () => {
  test('renders label', () => {
    render(<KPICard label="Total Balance" value="1,234.56" />)
    expect(screen.getByText('Total Balance')).toBeInTheDocument()
  })

  test('renders numeric value', () => {
    render(<KPICard label="Test" value="42,000.00" />)
    expect(screen.getByText('42,000.00')).toBeInTheDocument()
  })

  test('renders currency prefix', () => {
    render(<KPICard label="Balance" value="1,234.56" currency="GBP" />)
    expect(screen.getByText('GBP')).toBeInTheDocument()
  })

  test('shows positive delta', () => {
    render(
      <KPICard label="Test" value="100" delta={5.2} deltaDirection="up" />
    )
    expect(screen.getByText(/5\.2%/)).toBeInTheDocument()
  })

  test('shows negative delta', () => {
    render(
      <KPICard label="Test" value="100" delta={-3.1} deltaDirection="down" />
    )
    expect(screen.getByText(/-3\.1%/)).toBeInTheDocument()
  })

  test('shows delta label', () => {
    render(
      <KPICard label="Test" value="100" delta={1.0} deltaDirection="up" deltaLabel="vs last week" />
    )
    expect(screen.getByText('vs last week')).toBeInTheDocument()
  })

  test('renders loading skeleton when isLoading=true', () => {
    render(<KPICard label="Test" value="100" isLoading />)
    const el = screen.getByLabelText(/Loading Test/)
    expect(el).toBeInTheDocument()
    expect(el.getAttribute('aria-busy')).toBe('true')
  })

  test('value element has tabular-nums class', () => {
    render(<KPICard label="Test" value="1,000" />)
    // The value paragraph should have tabular-nums
    const container = screen.getByRole('article')
    const valueEl = container.querySelector('.tabular-nums')
    expect(valueEl).not.toBeNull()
  })

  test('has correct aria-label including currency and value', () => {
    render(<KPICard label="Balance" value="5,000" currency="GBP" />)
    expect(screen.getByRole('article', { name: /Balance.*GBP.*5,000/ })).toBeInTheDocument()
  })

  test('renders sparkline container when sparklineData provided', () => {
    const data = [{ value: 1 }, { value: 2 }, { value: 3 }]
    render(<KPICard label="Test" value="100" sparklineData={data} />)
    // recharts creates a div container
    const article = screen.getByRole('article')
    const sparklineContainer = article.querySelector('[aria-hidden="true"]')
    expect(sparklineContainer).not.toBeNull()
  })

  test('renders integer values correctly', () => {
    render(<KPICard label="Accounts" value={1247} />)
    expect(screen.getByText('1247')).toBeInTheDocument()
  })

  test('up delta has accessible aria-label', () => {
    render(
      <KPICard label="Test" value="100" delta={5.0} deltaDirection="up" deltaLabel="period" />
    )
    const deltaEl = screen.getByLabelText(/Increased by 5/)
    expect(deltaEl).toBeInTheDocument()
  })
})
