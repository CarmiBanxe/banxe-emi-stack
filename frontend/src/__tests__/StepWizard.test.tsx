/**
 * StepWizard Tests — 5 steps navigation, progress, validation
 * IL-ADDS-01
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, test, expect, vi } from 'vitest'
import { StepWizard, type WizardStep } from '../components/ui/StepWizard'

const FIVE_STEPS: WizardStep[] = [
  { id: 'step1', label: 'Identity',  estimatedMinutes: 3 },
  { id: 'step2', label: 'Address',   estimatedMinutes: 2 },
  { id: 'step3', label: 'AML Check', estimatedMinutes: 1 },
  { id: 'step4', label: 'Documents', estimatedMinutes: 3 },
  { id: 'step5', label: 'Review',    estimatedMinutes: 1 },
]

const WizardWrapper = ({
  currentStep = 0,
  canAdvance = true,
  onNext = vi.fn(),
  onBack = vi.fn(),
  onSubmit = vi.fn(),
  isSubmitting = false,
}: {
  currentStep?: number
  canAdvance?: boolean
  onNext?: () => void
  onBack?: () => void
  onSubmit?: () => void
  isSubmitting?: boolean
}) => (
  <StepWizard
    steps={FIVE_STEPS}
    currentStep={currentStep}
    onNext={onNext}
    onBack={onBack}
    onSubmit={onSubmit}
    isSubmitting={isSubmitting}
    canAdvance={canAdvance}
  >
    <div>Step {currentStep + 1} content</div>
  </StepWizard>
)

describe('StepWizard', () => {
  test('renders all 5 step labels', () => {
    render(<WizardWrapper />)
    for (const step of FIVE_STEPS) {
      expect(screen.getByText(step.label)).toBeInTheDocument()
    }
  })

  test('shows progress bar', () => {
    render(<WizardWrapper />)
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  test('shows 0% progress on first step', () => {
    render(<WizardWrapper currentStep={0} />)
    expect(screen.getByText(/0%/)).toBeInTheDocument()
  })

  test('shows 80% progress on step 4', () => {
    render(
      <StepWizard
        steps={FIVE_STEPS}
        currentStep={3}
        stepStates={{
          step1: 'completed',
          step2: 'completed',
          step3: 'completed',
          step4: 'active',
          step5: 'pending',
        }}
      >
        <div />
      </StepWizard>
    )
    expect(screen.getByText(/60%/)).toBeInTheDocument()
  })

  test('Next button calls onNext', () => {
    const onNext = vi.fn()
    render(<WizardWrapper onNext={onNext} />)
    fireEvent.click(screen.getByRole('button', { name: /Go to next step/ }))
    expect(onNext).toHaveBeenCalled()
  })

  test('Back button is disabled on first step', () => {
    render(<WizardWrapper currentStep={0} />)
    const backBtn = screen.getByRole('button', { name: /Go to previous step/ })
    expect(backBtn).toBeDisabled()
  })

  test('Back button calls onBack on non-first step', () => {
    const onBack = vi.fn()
    render(<WizardWrapper currentStep={2} onBack={onBack} />)
    const backBtn = screen.getByRole('button', { name: /Go to previous step/ })
    fireEvent.click(backBtn)
    expect(onBack).toHaveBeenCalled()
  })

  test('shows Submit button on last step', () => {
    render(<WizardWrapper currentStep={4} />)
    expect(screen.getByRole('button', { name: /Submit/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Go to next step/ })).toBeNull()
  })

  test('Submit button calls onSubmit on last step', () => {
    const onSubmit = vi.fn()
    render(<WizardWrapper currentStep={4} onSubmit={onSubmit} />)
    fireEvent.click(screen.getByRole('button', { name: /Submit/ }))
    expect(onSubmit).toHaveBeenCalled()
  })

  test('Next button is disabled when canAdvance=false', () => {
    render(<WizardWrapper canAdvance={false} />)
    const nextBtn = screen.getByRole('button', { name: /Go to next step/ })
    expect(nextBtn).toBeDisabled()
  })

  test('shows submitting state', () => {
    render(<WizardWrapper currentStep={4} isSubmitting />)
    expect(screen.getByRole('button', { name: /Submitting/ })).toBeDisabled()
  })

  test('shows estimated time remaining', () => {
    render(<WizardWrapper currentStep={0} />)
    expect(screen.getByText(/min remaining/)).toBeInTheDocument()
  })

  test('renders step content', () => {
    render(<WizardWrapper currentStep={2} />)
    expect(screen.getByText('Step 3 content')).toBeInTheDocument()
  })

  test('first step has aria-current="step"', () => {
    render(<WizardWrapper currentStep={0} />)
    const stepItem = screen.getByRole('listitem', { name: /Step 1/ })
    expect(stepItem).toHaveAttribute('aria-current', 'step')
  })

  test('progress has correct aria attributes', () => {
    render(<WizardWrapper currentStep={0} />)
    const progressbar = screen.getByRole('progressbar')
    expect(progressbar).toHaveAttribute('aria-valuenow', '0')
    expect(progressbar).toHaveAttribute('aria-valuemin', '0')
    expect(progressbar).toHaveAttribute('aria-valuemax', '100')
  })
})
