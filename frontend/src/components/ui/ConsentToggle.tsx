/**
 * ConsentToggle — GDPR Art.7 compliant consent component
 * Equal visual weight accept/reject — NO dark patterns
 * IL-ADDS-01
 */
import { Check, X } from 'lucide-react'

export type ConsentValue = 'accepted' | 'rejected' | null

export interface ConsentToggleProps {
  id: string
  title: string
  description: string
  value: ConsentValue
  onChange: (value: ConsentValue) => void
  required?: boolean
  disabled?: boolean
  'aria-describedby'?: string
}

/**
 * GDPR COMPLIANCE NOTE:
 * - Both Accept and Reject buttons are rendered with IDENTICAL visual weight
 * - Neither option is pre-selected or pre-checked
 * - Reject is never visually de-emphasized or hidden
 * - No greyed-out styling on reject option
 * - No manipulative language patterns
 */
export function ConsentToggle({
  id,
  title,
  description,
  value,
  onChange,
  required = false,
  disabled = false,
  'aria-describedby': ariaDescribedby,
}: ConsentToggleProps) {
  const acceptId = `${id}-accept`
  const rejectId = `${id}-reject`
  const descId   = `${id}-desc`

  return (
    <fieldset
      className="rounded-xl border border-[oklch(20%_0.01_240)] bg-[oklch(15%_0.01_240)] p-4"
      aria-describedby={ariaDescribedby ?? descId}
      disabled={disabled}
    >
      <legend className="text-sm font-semibold text-[oklch(95%_0_0)] mb-1">
        {title}
        {required && (
          <span className="ml-1 text-[#f87171]" aria-label="required">*</span>
        )}
      </legend>

      <p
        id={descId}
        className="text-xs text-[oklch(65%_0_0)] mb-4 leading-relaxed"
      >
        {description}
      </p>

      {/* Equal-weight buttons — GDPR Art.7 compliant */}
      <div className="flex gap-3" role="group" aria-label={`Consent for: ${title}`}>
        {/* Accept — same visual weight as Reject */}
        <label
          htmlFor={acceptId}
          className={`
            flex-1 flex items-center justify-center gap-2 cursor-pointer
            rounded-lg border-2 py-2.5 text-sm font-semibold
            transition-all duration-150 select-none
            ${disabled ? 'cursor-not-allowed opacity-50' : ''}
            ${value === 'accepted'
              ? 'border-[#10b981] bg-[#10b981]/15 text-[#34d399]'
              : 'border-[oklch(25%_0.01_240)] text-[oklch(65%_0_0)] hover:border-[#10b981]/50 hover:text-[#34d399]'
            }
          `}
        >
          <input
            type="radio"
            id={acceptId}
            name={id}
            value="accepted"
            checked={value === 'accepted'}
            onChange={() => onChange('accepted')}
            disabled={disabled}
            className="sr-only"
            aria-label={`Accept: ${title}`}
          />
          <Check size={15} aria-hidden="true" />
          Accept
        </label>

        {/* Reject — IDENTICAL visual weight to Accept */}
        <label
          htmlFor={rejectId}
          className={`
            flex-1 flex items-center justify-center gap-2 cursor-pointer
            rounded-lg border-2 py-2.5 text-sm font-semibold
            transition-all duration-150 select-none
            ${disabled ? 'cursor-not-allowed opacity-50' : ''}
            ${value === 'rejected'
              ? 'border-[#f43f5e] bg-[#f43f5e]/15 text-[#f87171]'
              : 'border-[oklch(25%_0.01_240)] text-[oklch(65%_0_0)] hover:border-[#f43f5e]/50 hover:text-[#f87171]'
            }
          `}
        >
          <input
            type="radio"
            id={rejectId}
            name={id}
            value="rejected"
            checked={value === 'rejected'}
            onChange={() => onChange('rejected')}
            disabled={disabled}
            className="sr-only"
            aria-label={`Reject: ${title}`}
          />
          <X size={15} aria-hidden="true" />
          Reject
        </label>
      </div>

      {/* Required + unset warning */}
      {required && value === null && (
        <p
          className="mt-2 text-xs text-[#fbbf24] flex items-center gap-1"
          role="alert"
          aria-live="polite"
        >
          This consent is required to proceed.
        </p>
      )}
    </fieldset>
  )
}

export default ConsentToggle
