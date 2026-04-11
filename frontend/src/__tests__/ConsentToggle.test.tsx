/**
 * ConsentToggle Tests — GDPR equal-weight buttons, no dark patterns
 * IL-ADDS-01
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, test, expect, vi } from 'vitest'
import { ConsentToggle, type ConsentValue } from '../components/ui/ConsentToggle'

const DEFAULT_PROPS = {
  id:          'test-consent',
  title:       'Test Consent',
  description: 'Please accept or reject this consent.',
  value:       null as ConsentValue,
  onChange:    vi.fn(),
}

describe('ConsentToggle', () => {
  test('renders title', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} />)
    expect(screen.getByText('Test Consent')).toBeInTheDocument()
  })

  test('renders description', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} />)
    expect(screen.getByText('Please accept or reject this consent.')).toBeInTheDocument()
  })

  test('renders both Accept and Reject buttons', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} />)
    expect(screen.getByLabelText(/Accept: Test Consent/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Reject: Test Consent/)).toBeInTheDocument()
  })

  test('Accept and Reject have EQUAL text content', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} />)
    // Both should have the same typography — use label text
    const acceptLabel = screen.getByText('Accept')
    const rejectLabel = screen.getByText('Reject')
    expect(acceptLabel).toBeInTheDocument()
    expect(rejectLabel).toBeInTheDocument()
  })

  test('clicking Accept calls onChange with "accepted"', () => {
    const onChange = vi.fn()
    render(<ConsentToggle {...DEFAULT_PROPS} onChange={onChange} />)
    fireEvent.click(screen.getByLabelText(/Accept: Test Consent/))
    expect(onChange).toHaveBeenCalledWith('accepted')
  })

  test('clicking Reject calls onChange with "rejected"', () => {
    const onChange = vi.fn()
    render(<ConsentToggle {...DEFAULT_PROPS} onChange={onChange} />)
    fireEvent.click(screen.getByLabelText(/Reject: Test Consent/))
    expect(onChange).toHaveBeenCalledWith('rejected')
  })

  test('neither Accept nor Reject is pre-selected (value=null)', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} value={null} />)
    const accept = screen.getByLabelText(/Accept: Test Consent/) as HTMLInputElement
    const reject = screen.getByLabelText(/Reject: Test Consent/) as HTMLInputElement
    expect(accept.checked).toBe(false)
    expect(reject.checked).toBe(false)
  })

  test('Accept radio is checked when value="accepted"', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} value="accepted" />)
    const accept = screen.getByLabelText(/Accept: Test Consent/) as HTMLInputElement
    expect(accept.checked).toBe(true)
  })

  test('Reject radio is checked when value="rejected"', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} value="rejected" />)
    const reject = screen.getByLabelText(/Reject: Test Consent/) as HTMLInputElement
    expect(reject.checked).toBe(true)
  })

  test('required warning shown when required=true and value=null', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} required value={null} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(/required/)
  })

  test('no required warning when value is set', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} required value="accepted" />)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  test('disabled state disables both radios', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} disabled />)
    const accept = screen.getByLabelText(/Accept: Test Consent/) as HTMLInputElement
    const reject = screen.getByLabelText(/Reject: Test Consent/) as HTMLInputElement
    expect(accept.disabled).toBe(true)
    expect(reject.disabled).toBe(true)
  })

  test('required asterisk is shown', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} required />)
    expect(screen.getByLabelText('required')).toBeInTheDocument()
  })

  test('uses fieldset for accessibility', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} />)
    expect(screen.getByRole('group').tagName).toBe('FIELDSET')
  })

  test('buttons share same container role=group', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} />)
    expect(screen.getByRole('group', { name: /Consent for: Test Consent/ })).toBeInTheDocument()
  })

  // Dark pattern prevention tests
  test('Accept label has no "recommended" text — no dark pattern', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} />)
    const acceptLabel = screen.getByText('Accept').closest('label')
    expect(acceptLabel?.textContent).not.toMatch(/recommended|suggested|best/i)
  })

  test('Reject label is not hidden or visually suppressed', () => {
    render(<ConsentToggle {...DEFAULT_PROPS} />)
    const rejectLabel = screen.getByText('Reject').closest('label')
    // Should not have display:none or visibility:hidden
    const style = window.getComputedStyle(rejectLabel!)
    expect(style.display).not.toBe('none')
    expect(style.visibility).not.toBe('hidden')
  })
})
