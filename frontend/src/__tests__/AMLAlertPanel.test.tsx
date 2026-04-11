/**
 * AMLAlertPanel Tests — severity border colors, CTA
 * IL-ADDS-01
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, test, expect, vi } from 'vitest'
import { AMLAlertPanel, type AMLAlert } from '../components/ui/AMLAlertPanel'

const makeAlert = (severity: AMLAlert['severity'], overrides?: Partial<AMLAlert>): AMLAlert => ({
  id:          `AML-TEST-${severity}`,
  severity,
  title:       `Test ${severity} alert`,
  description: `Test description for ${severity}`,
  timestamp:   '2026-04-11T10:00:00Z',
  ...overrides,
})

describe('AMLAlertPanel', () => {
  test('renders CRITICAL alert', () => {
    render(<AMLAlertPanel alert={makeAlert('CRITICAL')} />)
    expect(screen.getByText('Test CRITICAL alert')).toBeInTheDocument()
    expect(screen.getByText('CRITICAL')).toBeInTheDocument()
  })

  test('renders HIGH alert', () => {
    render(<AMLAlertPanel alert={makeAlert('HIGH')} />)
    expect(screen.getByText('HIGH')).toBeInTheDocument()
  })

  test('renders MEDIUM alert', () => {
    render(<AMLAlertPanel alert={makeAlert('MEDIUM')} />)
    expect(screen.getByText('MEDIUM')).toBeInTheDocument()
  })

  test('renders LOW alert', () => {
    render(<AMLAlertPanel alert={makeAlert('LOW')} />)
    expect(screen.getByText('LOW')).toBeInTheDocument()
  })

  test('CRITICAL uses #f43f5e border color', () => {
    render(<AMLAlertPanel alert={makeAlert('CRITICAL')} />)
    const article = screen.getByRole('article')
    expect(article.style.borderLeftColor).toBe('#f43f5e')
  })

  test('HIGH uses #f97316 border color', () => {
    render(<AMLAlertPanel alert={makeAlert('HIGH')} />)
    const article = screen.getByRole('article')
    expect(article.style.borderLeftColor).toBe('#f97316')
  })

  test('MEDIUM uses #f59e0b border color', () => {
    render(<AMLAlertPanel alert={makeAlert('MEDIUM')} />)
    const article = screen.getByRole('article')
    expect(article.style.borderLeftColor).toBe('#f59e0b')
  })

  test('has data-severity attribute matching severity level', () => {
    render(<AMLAlertPanel alert={makeAlert('CRITICAL')} />)
    const article = screen.getByRole('article')
    expect(article.getAttribute('data-severity')).toBe('critical')
  })

  test('shows Review CTA when onReview provided', () => {
    render(<AMLAlertPanel alert={makeAlert('HIGH')} onReview={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Review/ })).toBeInTheDocument()
  })

  test('Review button calls onReview with alert ID', () => {
    const handleReview = vi.fn()
    const alert = makeAlert('HIGH')
    render(<AMLAlertPanel alert={alert} onReview={handleReview} />)
    fireEvent.click(screen.getByRole('button', { name: /Review/ }))
    expect(handleReview).toHaveBeenCalledWith(alert.id)
  })

  test('hides Review CTA when onReview not provided', () => {
    render(<AMLAlertPanel alert={makeAlert('LOW')} />)
    expect(screen.queryByRole('button', { name: /Review/ })).toBeNull()
  })

  test('shows amount and currency when provided', () => {
    render(
      <AMLAlertPanel
        alert={makeAlert('HIGH', { amount: '55,000.00', currency: 'USD' })}
      />
    )
    expect(screen.getByText(/USD/)).toBeInTheDocument()
    expect(screen.getByText(/55,000\.00/)).toBeInTheDocument()
  })

  test('shows rule ID when provided', () => {
    render(<AMLAlertPanel alert={makeAlert('HIGH', { ruleId: 'AML-R-042' })} />)
    expect(screen.getByText('[AML-R-042]')).toBeInTheDocument()
  })

  test('shows account ID when provided', () => {
    render(<AMLAlertPanel alert={makeAlert('HIGH', { accountId: 'ACC-9999' })} />)
    expect(screen.getByText('ACC-9999')).toBeInTheDocument()
  })

  test('hides description in compact mode', () => {
    const alert = makeAlert('HIGH')
    render(<AMLAlertPanel alert={alert} compact />)
    expect(screen.queryByText(alert.description)).toBeNull()
  })

  test('shows description in normal mode', () => {
    const alert = makeAlert('HIGH')
    render(<AMLAlertPanel alert={alert} />)
    expect(screen.getByText(alert.description)).toBeInTheDocument()
  })

  test('has accessible article role with aria-label', () => {
    render(<AMLAlertPanel alert={makeAlert('CRITICAL')} />)
    expect(screen.getByRole('article')).toHaveAttribute('aria-label')
  })
})
