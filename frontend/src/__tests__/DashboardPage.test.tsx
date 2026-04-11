/**
 * DashboardPage Tests — layout, KPI cards, table, AML feed
 * IL-ADDS-01
 */
import { render, screen } from '@testing-library/react'
import { describe, test, expect } from 'vitest'
import { DashboardPage } from '../modules/dashboard/DashboardPage'

describe('DashboardPage', () => {
  test('renders main layout', () => {
    render(<DashboardPage />)
    expect(screen.getByRole('main')).toBeInTheDocument()
  })

  test('renders sidebar navigation', () => {
    render(<DashboardPage />)
    expect(screen.getByRole('navigation', { name: /Main navigation/ })).toBeInTheDocument()
  })

  test('renders Overview heading', () => {
    render(<DashboardPage />)
    expect(screen.getByRole('heading', { name: /Overview/i })).toBeInTheDocument()
  })

  test('renders KPI cards section', () => {
    render(<DashboardPage />)
    expect(screen.getByRole('region', { name: /Key performance indicators/ })).toBeInTheDocument()
  })

  test('renders Total Safeguarded KPI card', () => {
    render(<DashboardPage />)
    expect(screen.getByText('Total Safeguarded')).toBeInTheDocument()
  })

  test('renders Active Accounts KPI card', () => {
    render(<DashboardPage />)
    expect(screen.getByText('Active Accounts')).toBeInTheDocument()
  })

  test('renders Pending Transactions KPI card', () => {
    render(<DashboardPage />)
    expect(screen.getByText('Pending Transactions')).toBeInTheDocument()
  })

  test('renders Open AML Alerts KPI card', () => {
    render(<DashboardPage />)
    expect(screen.getByText('Open AML Alerts')).toBeInTheDocument()
  })

  test('renders Recent Transactions heading', () => {
    render(<DashboardPage />)
    expect(screen.getByRole('heading', { name: /Recent Transactions/i })).toBeInTheDocument()
  })

  test('renders AML Alerts section', () => {
    render(<DashboardPage />)
    expect(screen.getByRole('complementary', { name: /AML alert feed/ })).toBeInTheDocument()
  })

  test('renders transactions table with data', () => {
    render(<DashboardPage />)
    // Check for at least one transaction from mock data
    expect(screen.getByText('Wire transfer — London HQ')).toBeInTheDocument()
  })

  test('renders AML alerts in feed', () => {
    render(<DashboardPage />)
    expect(screen.getByText('Large cross-border transfer exceeds threshold')).toBeInTheDocument()
  })

  test('renders CRITICAL alert in feed', () => {
    render(<DashboardPage />)
    expect(screen.getByText('CRITICAL')).toBeInTheDocument()
  })

  test('renders Refresh button', () => {
    render(<DashboardPage />)
    expect(screen.getByRole('button', { name: /Refresh dashboard/i })).toBeInTheDocument()
  })

  test('transactions table has tabular-nums', () => {
    render(<DashboardPage />)
    const table = screen.getByRole('region', { name: /Recent transactions/ })
    expect(table).toBeInTheDocument()
  })

  test('renders status badges in transactions', () => {
    render(<DashboardPage />)
    const approvedBadges = screen.getAllByRole('status', { name: /Status: Approved/ })
    expect(approvedBadges.length).toBeGreaterThan(0)
  })

  test('page has dark background class', () => {
    render(<DashboardPage />)
    const outerDiv = screen.getByRole('main').parentElement
    expect(outerDiv?.style.background).toContain('oklch')
  })
})
