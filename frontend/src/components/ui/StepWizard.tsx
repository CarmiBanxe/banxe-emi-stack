/**
 * StepWizard — Multi-step wizard with progress indicator
 * Used by KYC Wizard (5 steps), Back/Next navigation, form validation
 * IL-ADDS-01
 */
import { CheckCircle2, Circle, Loader2 } from 'lucide-react'

export interface WizardStep {
  id: string
  label: string
  description?: string
  estimatedMinutes?: number
}

export type StepState = 'completed' | 'active' | 'pending' | 'error'

export interface StepWizardProps {
  steps: WizardStep[]
  currentStep: number
  stepStates?: Record<string, StepState>
  onNext?: () => void | Promise<void>
  onBack?: () => void
  onSubmit?: () => void | Promise<void>
  isSubmitting?: boolean
  canAdvance?: boolean
  children: React.ReactNode
  submitLabel?: string
}

function StepIndicator({
  step,
  index,
  state,
  current,
  total,
}: {
  step: WizardStep
  index: number
  state: StepState
  current: number
  total: number
}) {
  const isCompleted = state === 'completed'
  const isActive    = state === 'active'
  const isError     = state === 'error'

  let circleClass = 'border-2 transition-colors duration-200 '
  let numClass    = 'text-xs font-bold '

  if (isCompleted) {
    circleClass += 'border-[#10b981] bg-[#10b981]/20'
    numClass    += 'text-[#34d399]'
  } else if (isActive) {
    circleClass += 'border-[#3b82f6] bg-[#3b82f6]/20'
    numClass    += 'text-[#60a5fa]'
  } else if (isError) {
    circleClass += 'border-[#f43f5e] bg-[#f43f5e]/20'
    numClass    += 'text-[#f87171]'
  } else {
    circleClass += 'border-[oklch(25%_0.01_240)] bg-transparent'
    numClass    += 'text-[oklch(45%_0_0)]'
  }

  return (
    <li
      className="flex flex-col items-center relative"
      aria-current={isActive ? 'step' : undefined}
    >
      {/* Connector line */}
      {index < total - 1 && (
        <div
          className="absolute top-4 left-1/2 w-full h-0.5 transition-colors duration-300"
          style={{
            background: isCompleted ? '#10b981' : 'oklch(20% 0.01 240)',
            left: '50%',
          }}
          aria-hidden="true"
        />
      )}

      {/* Circle */}
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${circleClass}`}
        aria-label={`Step ${index + 1}: ${step.label} — ${state}`}
      >
        {isCompleted ? (
          <CheckCircle2 size={16} className="text-[#34d399]" aria-hidden="true" />
        ) : (
          <span className={numClass}>{index + 1}</span>
        )}
      </div>

      {/* Label */}
      <span
        className={`
          mt-1.5 text-xs font-medium text-center max-w-[72px] leading-tight
          ${isActive ? 'text-[oklch(95%_0_0)]' : isCompleted ? 'text-[oklch(65%_0_0)]' : 'text-[oklch(45%_0_0)]'}
        `}
      >
        {step.label}
      </span>
    </li>
  )
}

function computeProgress(steps: WizardStep[], stepStates: Record<string, StepState>): number {
  const completedCount = steps.filter(s => stepStates[s.id] === 'completed').length
  return Math.round((completedCount / steps.length) * 100)
}

function estimateRemaining(steps: WizardStep[], currentStep: number): number {
  return steps
    .slice(currentStep)
    .reduce((acc, s) => acc + (s.estimatedMinutes ?? 2), 0)
}

export function StepWizard({
  steps,
  currentStep,
  stepStates: externalStates,
  onNext,
  onBack,
  onSubmit,
  isSubmitting = false,
  canAdvance = true,
  children,
  submitLabel = 'Submit',
}: StepWizardProps) {
  const stepStates: Record<string, StepState> = externalStates ?? {}
  steps.forEach((s, i) => {
    if (!stepStates[s.id]) {
      stepStates[s.id] = i < currentStep ? 'completed' : i === currentStep ? 'active' : 'pending'
    }
  })

  const progress = computeProgress(steps, stepStates)
  const remainingMin = estimateRemaining(steps, currentStep)
  const isLastStep = currentStep === steps.length - 1

  return (
    <div className="flex flex-col gap-6">
      {/* Progress header */}
      <div
        className="
          rounded-xl border border-[oklch(20%_0.01_240)]
          bg-[oklch(13%_0.01_240)] px-6 py-4
        "
        role="progressbar"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Wizard progress: ${progress}% complete`}
      >
        {/* Step indicators */}
        <ol className="flex justify-between mb-4" aria-label="Wizard steps">
          {steps.map((step, i) => (
            <StepIndicator
              key={step.id}
              step={step}
              index={i}
              state={stepStates[step.id] ?? 'pending'}
              current={currentStep}
              total={steps.length}
            />
          ))}
        </ol>

        {/* Progress bar */}
        <div className="w-full h-1.5 rounded-full bg-[oklch(20%_0.01_240)] mb-2">
          <div
            className="h-full rounded-full bg-[#3b82f6] transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>

        <div className="flex justify-between text-xs text-[oklch(45%_0_0)]">
          <span>{progress}% complete</span>
          {remainingMin > 0 && (
            <span>~{remainingMin} min remaining</span>
          )}
        </div>
      </div>

      {/* Step content */}
      <div
        className="
          rounded-xl border border-[oklch(20%_0.01_240)]
          bg-[oklch(15%_0.01_240)] p-6
        "
        aria-live="polite"
        aria-atomic="true"
      >
        {children}
      </div>

      {/* Navigation */}
      <div className="flex justify-between gap-3">
        <button
          onClick={onBack}
          disabled={currentStep === 0 || isSubmitting}
          className="
            px-4 py-2 rounded-lg text-sm font-medium
            border border-[oklch(25%_0.01_240)]
            text-[oklch(65%_0_0)] hover:text-[oklch(95%_0_0)]
            hover:border-[oklch(35%_0.01_240)]
            disabled:opacity-40 disabled:cursor-not-allowed
            transition-colors duration-150
          "
          aria-label="Go to previous step"
        >
          Back
        </button>

        {isLastStep ? (
          <button
            onClick={onSubmit}
            disabled={!canAdvance || isSubmitting}
            className="
              inline-flex items-center gap-2
              px-6 py-2 rounded-lg text-sm font-semibold
              bg-[#3b82f6] text-white
              hover:bg-[#2563eb]
              disabled:opacity-40 disabled:cursor-not-allowed
              transition-colors duration-150
            "
            aria-label={isSubmitting ? 'Submitting...' : submitLabel}
          >
            {isSubmitting && (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            )}
            {isSubmitting ? 'Submitting...' : submitLabel}
          </button>
        ) : (
          <button
            onClick={onNext}
            disabled={!canAdvance || isSubmitting}
            className="
              px-6 py-2 rounded-lg text-sm font-semibold
              bg-[#3b82f6] text-white
              hover:bg-[#2563eb]
              disabled:opacity-40 disabled:cursor-not-allowed
              transition-colors duration-150
            "
            aria-label="Go to next step"
          >
            Next
          </button>
        )}
      </div>
    </div>
  )
}

export default StepWizard
