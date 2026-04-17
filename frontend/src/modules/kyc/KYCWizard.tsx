/**
 * KYCWizard — 5-step KYC onboarding wizard
 * React Hook Form, file upload, consent, mobile responsive
 * IL-ADDS-01 | GDPR Art.7 | FCA CASS 15
 */

import { AlertTriangle, CheckCircle2, FileText, Loader2, Upload, X } from "lucide-react";
import { useCallback, useState } from "react";
import { useForm } from "react-hook-form";
import { ConsentToggle, type ConsentValue } from "../../components/ui/ConsentToggle";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { type StepState, StepWizard, type WizardStep } from "../../components/ui/StepWizard";

// ─── Step types ────────────────────────────────────────────────────────────────

interface PersonalIdentityForm {
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  nationality: string;
  taxId: string;
}

interface AddressForm {
  country: string;
  addressLine1: string;
  addressLine2?: string;
  city: string;
  postcode: string;
}

interface UploadedFile {
  name: string;
  size: number;
  type: string;
  dataUrl?: string;
}

interface ConsentForm {
  amlScreening: ConsentValue;
  dataProcessing: ConsentValue;
  marketingComms: ConsentValue;
}

// ─── Wizard steps definition ──────────────────────────────────────────────────

const WIZARD_STEPS: WizardStep[] = [
  { id: "identity", label: "Identity", estimatedMinutes: 3 },
  { id: "address", label: "Address", estimatedMinutes: 2 },
  { id: "aml", label: "AML Check", estimatedMinutes: 1 },
  { id: "documents", label: "Documents", estimatedMinutes: 3 },
  { id: "review", label: "Review", estimatedMinutes: 1 },
];

// ─── Shared field component ────────────────────────────────────────────────────

function Field({
  label,
  error,
  required,
  children,
}: {
  label: string;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-semibold text-[oklch(65%_0_0)] uppercase tracking-wide">
        {label}
        {required && (
          <span className="ml-1 text-[#f87171]" aria-label="required">
            *
          </span>
        )}
      </label>
      {children}
      {error && (
        <p className="text-xs text-[#f87171] flex items-center gap-1" role="alert">
          <AlertTriangle size={11} aria-hidden="true" />
          {error}
        </p>
      )}
    </div>
  );
}

const inputClass = `
  w-full px-3 py-2 rounded-lg text-sm
  bg-[oklch(13%_0.01_240)] border border-[oklch(25%_0.01_240)]
  text-[oklch(95%_0_0)] placeholder:text-[oklch(35%_0_0)]
  focus:outline-none focus:border-[#3b82f6] focus:ring-1 focus:ring-[#3b82f6]/30
  transition-colors duration-150
`;

// ─── Step 1: Personal Identity ─────────────────────────────────────────────────

function PersonalIdentityStep({
  onComplete,
  defaultValues,
}: {
  onComplete: (data: PersonalIdentityForm) => void;
  defaultValues?: Partial<PersonalIdentityForm>;
}) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<PersonalIdentityForm>({
    defaultValues,
  });

  return (
    <form
      id="step-identity-form"
      onSubmit={handleSubmit(onComplete)}
      className="grid grid-cols-1 sm:grid-cols-2 gap-4"
      noValidate
    >
      <h2 className="sm:col-span-2 text-base font-bold text-[oklch(95%_0_0)]">Personal Identity</h2>
      <Field label="First Name" error={errors.firstName?.message} required>
        <input
          {...register("firstName", { required: "First name is required" })}
          type="text"
          className={inputClass}
          placeholder="John"
          autoComplete="given-name"
          aria-required="true"
        />
      </Field>
      <Field label="Last Name" error={errors.lastName?.message} required>
        <input
          {...register("lastName", { required: "Last name is required" })}
          type="text"
          className={inputClass}
          placeholder="Smith"
          autoComplete="family-name"
          aria-required="true"
        />
      </Field>
      <Field label="Date of Birth" error={errors.dateOfBirth?.message} required>
        <input
          {...register("dateOfBirth", {
            required: "Date of birth is required",
            validate: (v) => {
              const age = (Date.now() - new Date(v).getTime()) / (1000 * 60 * 60 * 24 * 365.25);
              return age >= 18 || "Must be at least 18 years old";
            },
          })}
          type="date"
          className={inputClass}
          autoComplete="bday"
          aria-required="true"
        />
      </Field>
      <Field label="Nationality" error={errors.nationality?.message} required>
        <input
          {...register("nationality", { required: "Nationality is required" })}
          type="text"
          className={inputClass}
          placeholder="British"
          autoComplete="country-name"
          aria-required="true"
        />
      </Field>
      <Field label="Tax ID / NI Number" error={errors.taxId?.message} required>
        <input
          {...register("taxId", { required: "Tax ID is required" })}
          type="text"
          className={`${inputClass} sm:col-span-2 font-mono`}
          placeholder="AB 12 34 56 C"
          aria-required="true"
          aria-describedby="tax-id-hint"
        />
        <span id="tax-id-hint" className="text-xs text-[oklch(45%_0_0)]">
          UK National Insurance or Tax Reference Number
        </span>
      </Field>
    </form>
  );
}

// ─── Step 2: Address Verification ─────────────────────────────────────────────

function AddressStep({
  onComplete,
  defaultValues,
}: {
  onComplete: (data: AddressForm) => void;
  defaultValues?: Partial<AddressForm>;
}) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<AddressForm>({
    defaultValues,
  });

  return (
    <form
      id="step-address-form"
      onSubmit={handleSubmit(onComplete)}
      className="grid grid-cols-1 sm:grid-cols-2 gap-4"
      noValidate
    >
      <h2 className="sm:col-span-2 text-base font-bold text-[oklch(95%_0_0)]">Address Verification</h2>
      <Field label="Country" error={errors.country?.message} required>
        <select
          {...register("country", { required: "Country is required" })}
          className={inputClass}
          aria-required="true"
        >
          <option value="">Select country…</option>
          <option value="GB">United Kingdom</option>
          <option value="DE">Germany</option>
          <option value="FR">France</option>
          <option value="NL">Netherlands</option>
          <option value="IE">Ireland</option>
        </select>
      </Field>
      <Field label="Post Code" error={errors.postcode?.message} required>
        <input
          {...register("postcode", {
            required: "Postcode is required",
            pattern: { value: /^[A-Z]{1,2}\d[A-Z\d]? \d[A-Z]{2}$/i, message: "Invalid UK postcode" },
          })}
          type="text"
          className={`${inputClass} uppercase`}
          placeholder="SW1A 2AA"
          autoComplete="postal-code"
          aria-required="true"
        />
      </Field>
      <Field label="Address Line 1" error={errors.addressLine1?.message} required>
        <input
          {...register("addressLine1", { required: "Address is required" })}
          type="text"
          className={inputClass}
          placeholder="10 Downing Street"
          autoComplete="address-line1"
          aria-required="true"
        />
      </Field>
      <Field label="Address Line 2">
        <input
          {...register("addressLine2")}
          type="text"
          className={inputClass}
          placeholder="Flat / Floor (optional)"
          autoComplete="address-line2"
        />
      </Field>
      <Field label="City" error={errors.city?.message} required>
        <input
          {...register("city", { required: "City is required" })}
          type="text"
          className={inputClass}
          placeholder="London"
          autoComplete="address-level2"
          aria-required="true"
        />
      </Field>
    </form>
  );
}

// ─── Step 3: AML Pre-screening ─────────────────────────────────────────────────

type AMLScreeningState = "idle" | "running" | "passed" | "failed" | "review";

function AMLScreeningStep({ autoStart = true }: { autoStart?: boolean }) {
  const [state, setState] = useState<AMLScreeningState>(autoStart ? "running" : "idle");
  const [progress, setProgress] = useState(0);

  // Simulate AML screening
  const runScreening = useCallback(() => {
    setState("running");
    setProgress(0);
    const intervals = [20, 45, 70, 90, 100];
    let i = 0;
    const timer = setInterval(() => {
      if (i < intervals.length) {
        setProgress(intervals[i++]);
      } else {
        clearInterval(timer);
        setState("passed"); // In real impl: call AML API
      }
    }, 600);
  }, []);

  if (state === "idle") {
    return (
      <div className="flex flex-col items-center gap-4 py-8">
        <h2 className="text-base font-bold text-[oklch(95%_0_0)]">AML Pre-screening</h2>
        <p className="text-sm text-[oklch(65%_0_0)] text-center max-w-sm">
          Automated screening against sanctions lists, PEP databases, and adverse media.
        </p>
        <button
          onClick={runScreening}
          className="px-6 py-2.5 rounded-lg bg-[#3b82f6] text-white text-sm font-semibold hover:bg-[#2563eb] transition-colors"
        >
          Start Screening
        </button>
      </div>
    );
  }

  if (state === "running") {
    return (
      <div className="flex flex-col items-center gap-4 py-8" aria-live="polite" aria-busy="true">
        <h2 className="text-base font-bold text-[oklch(95%_0_0)]">AML Pre-screening</h2>
        <Loader2 size={32} className="animate-spin text-[#3b82f6]" aria-hidden="true" />
        <p className="text-sm text-[oklch(65%_0_0)]">Running automated checks…</p>
        <div className="w-64 h-2 rounded-full bg-[oklch(20%_0.01_240)]">
          <div
            className="h-full rounded-full bg-[#3b82f6] transition-all duration-500"
            style={{ width: `${progress}%` }}
            role="progressbar"
            aria-valuenow={progress}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Screening progress: ${progress}%`}
          />
        </div>
        <ul className="text-xs text-[oklch(45%_0_0)] space-y-1 text-center">
          <li className={progress >= 20 ? "text-[#34d399]" : ""}>✓ Sanctions list (OFAC, EU, UN)</li>
          <li className={progress >= 45 ? "text-[#34d399]" : ""}>✓ PEP database check</li>
          <li className={progress >= 70 ? "text-[#34d399]" : ""}>✓ Adverse media screening</li>
          <li className={progress >= 90 ? "text-[#34d399]" : ""}>✓ Internal watchlist</li>
          <li className={progress >= 100 ? "text-[#34d399]" : ""}>✓ Risk scoring</li>
        </ul>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-4 py-8" aria-live="polite">
      <h2 className="text-base font-bold text-[oklch(95%_0_0)]">AML Pre-screening</h2>
      {state === "passed" && (
        <>
          <CheckCircle2 size={48} className="text-[#10b981]" aria-hidden="true" />
          <StatusBadge status="APPROVED" showIcon />
          <p className="text-sm text-[oklch(65%_0_0)] text-center max-w-sm">
            No matches found in sanctions lists, PEP databases, or adverse media. Proceed to document upload.
          </p>
        </>
      )}
      {state === "failed" && (
        <>
          <AlertTriangle size={48} className="text-[#f43f5e]" aria-hidden="true" />
          <StatusBadge status="REJECTED" showIcon />
          <p className="text-sm text-[oklch(65%_0_0)] text-center max-w-sm">
            AML screening identified a match. This application requires manual review.
          </p>
        </>
      )}
      {state === "review" && (
        <>
          <AlertTriangle size={48} className="text-[#f59e0b]" aria-hidden="true" />
          <StatusBadge status="UNDER_REVIEW" showIcon />
          <p className="text-sm text-[oklch(65%_0_0)] text-center max-w-sm">
            Enhanced Due Diligence required. A compliance officer will contact you within 2 business days.
          </p>
        </>
      )}
    </div>
  );
}

// ─── Step 4: Document Upload ───────────────────────────────────────────────────

const ACCEPTED_TYPES = ["image/jpeg", "image/png", "application/pdf"];
const MAX_SIZE_BYTES = 10 * 1024 * 1024; // 10MB

function DocumentUploadStep({
  onFilesChange,
  files,
}: {
  onFilesChange: (key: string, file: UploadedFile | null) => void;
  files: Record<string, UploadedFile | null>;
}) {
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const handleDrop = useCallback(
    (key: string, fileList: FileList | null) => {
      const file = fileList?.[0];
      if (!file) return;

      const errs: Record<string, string> = {};
      if (!ACCEPTED_TYPES.includes(file.type)) {
        errs[key] = "Accepted formats: PDF, JPG, PNG";
      }
      if (file.size > MAX_SIZE_BYTES) {
        errs[key] = `File too large. Max size: 10MB (current: ${(file.size / 1024 / 1024).toFixed(1)}MB)`;
      }

      if (errs[key]) {
        setErrors((prev) => ({ ...prev, ...errs }));
        return;
      }

      setErrors((prev) => ({ ...prev, [key]: "" }));

      // Simulate upload progress
      let progress = 0;
      const timer = setInterval(() => {
        progress += 20;
        setUploadProgress((prev) => ({ ...prev, [key]: progress }));
        if (progress >= 100) {
          clearInterval(timer);
          onFilesChange(key, {
            name: file.name,
            size: file.size,
            type: file.type,
          });
        }
      }, 200);
    },
    [onFilesChange],
  );

  const docSlots = [
    { key: "passport", label: "Passport / National ID (front)", required: true },
    { key: "id_back", label: "Passport / National ID (back)", required: false },
    { key: "selfie", label: "Selfie with document", required: true },
    { key: "proof_of_address", label: "Proof of address (utility bill, bank statement)", required: false },
  ];

  return (
    <div className="space-y-4">
      <h2 className="text-base font-bold text-[oklch(95%_0_0)]">Document Upload</h2>
      <p className="text-xs text-[oklch(45%_0_0)]">Accepted: PDF, JPG, PNG — Max 10MB per file</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {docSlots.map((slot) => {
          const uploaded = files[slot.key];
          const progress = uploadProgress[slot.key] ?? 0;
          const err = errors[slot.key];

          return (
            <div key={slot.key} className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-[oklch(65%_0_0)] uppercase tracking-wide">
                {slot.label}
                {slot.required && <span className="ml-1 text-[#f87171]">*</span>}
              </span>

              {uploaded ? (
                <div
                  className="
                    flex items-center gap-2 px-3 py-2.5 rounded-lg
                    border border-[#10b981]/30 bg-[#10b981]/10
                  "
                >
                  <FileText size={16} className="text-[#34d399] shrink-0" aria-hidden="true" />
                  <span className="text-xs text-[oklch(95%_0_0)] truncate flex-1">{uploaded.name}</span>
                  <span className="text-xs text-[oklch(45%_0_0)]">{(uploaded.size / 1024).toFixed(0)}KB</span>
                  <button
                    onClick={() => onFilesChange(slot.key, null)}
                    className="text-[oklch(45%_0_0)] hover:text-[#f87171] transition-colors"
                    aria-label={`Remove ${slot.label}`}
                  >
                    <X size={13} aria-hidden="true" />
                  </button>
                </div>
              ) : progress > 0 && progress < 100 ? (
                <div className="px-3 py-2.5 rounded-lg border border-[oklch(25%_0.01_240)] bg-[oklch(13%_0.01_240)]">
                  <div className="flex items-center gap-2 mb-1.5">
                    <Loader2 size={13} className="animate-spin text-[#3b82f6]" aria-hidden="true" />
                    <span className="text-xs text-[oklch(65%_0_0)]">Uploading… {progress}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-[oklch(20%_0.01_240)]">
                    <div
                      className="h-full rounded-full bg-[#3b82f6] transition-all duration-200"
                      style={{ width: `${progress}%` }}
                      role="progressbar"
                      aria-valuenow={progress}
                      aria-valuemin={0}
                      aria-valuemax={100}
                    />
                  </div>
                </div>
              ) : (
                <label
                  className={`
                    flex flex-col items-center justify-center gap-2 px-3 py-4
                    rounded-lg border-2 border-dashed cursor-pointer
                    transition-colors duration-150 text-center
                    ${
                      err
                        ? "border-[#f43f5e]/50 bg-[#f43f5e]/5"
                        : "border-[oklch(25%_0.01_240)] hover:border-[#3b82f6]/50 hover:bg-[#3b82f6]/5"
                    }
                  `}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    handleDrop(slot.key, e.dataTransfer.files);
                  }}
                  aria-label={`Upload ${slot.label}`}
                >
                  <input
                    type="file"
                    accept={ACCEPTED_TYPES.join(",")}
                    className="sr-only"
                    onChange={(e) => handleDrop(slot.key, e.target.files)}
                    aria-label={`Choose file for ${slot.label}`}
                  />
                  <Upload size={20} className={err ? "text-[#f87171]" : "text-[oklch(45%_0_0)]"} aria-hidden="true" />
                  <span className="text-xs text-[oklch(45%_0_0)]">Drop file or click to browse</span>
                </label>
              )}

              {err && (
                <p className="text-xs text-[#f87171] flex items-center gap-1" role="alert">
                  <AlertTriangle size={10} aria-hidden="true" />
                  {err}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Step 5: Review + Consent ─────────────────────────────────────────────────

function ReviewStep({
  identity,
  address,
  onConsentChange,
  consents,
}: {
  identity: Partial<PersonalIdentityForm>;
  address: Partial<AddressForm>;
  onConsentChange: (key: string, value: ConsentValue) => void;
  consents: ConsentForm;
}) {
  return (
    <div className="space-y-4">
      <h2 className="text-base font-bold text-[oklch(95%_0_0)]">Review & Submit</h2>

      {/* Summary */}
      <div className="rounded-lg border border-[oklch(20%_0.01_240)] bg-[oklch(13%_0.01_240)] p-4 space-y-2">
        <p className="text-xs uppercase tracking-widest font-semibold text-[oklch(45%_0_0)] mb-3">
          Application Summary
        </p>
        {[
          ["Name", `${identity.firstName ?? "—"} ${identity.lastName ?? "—"}`],
          ["Date of Birth", identity.dateOfBirth ?? "—"],
          ["Nationality", identity.nationality ?? "—"],
          ["Address", address.city ? `${address.city}, ${address.country}` : "—"],
        ].map(([label, value]) => (
          <div key={label} className="flex justify-between text-sm">
            <span className="text-[oklch(65%_0_0)]">{label}</span>
            <span className="text-[oklch(95%_0_0)] font-medium">{value}</span>
          </div>
        ))}
      </div>

      {/* Required consents */}
      <ConsentToggle
        id="consent-aml"
        title="AML / Identity Verification"
        description="I consent to my data being processed for Anti-Money Laundering checks, sanctions screening, and identity verification as required under MLR 2017 and FCA CASS 15."
        value={consents.amlScreening}
        onChange={(v) => onConsentChange("amlScreening", v)}
        required
      />
      <ConsentToggle
        id="consent-data"
        title="Data Processing (GDPR Art.6)"
        description="I consent to BANXE processing my personal data for account management purposes in accordance with our Privacy Policy and UK GDPR."
        value={consents.dataProcessing}
        onChange={(v) => onConsentChange("dataProcessing", v)}
        required
      />
      <ConsentToggle
        id="consent-marketing"
        title="Marketing Communications"
        description="I agree to receive product updates and offers from BANXE via email and push notifications. You can withdraw consent at any time."
        value={consents.marketingComms}
        onChange={(v) => onConsentChange("marketingComms", v)}
      />
    </div>
  );
}

// ─── Main KYCWizard ───────────────────────────────────────────────────────────

export function KYCWizard() {
  const [currentStep, setCurrentStep] = useState(0);
  const [stepStates, setStepStates] = useState<Record<string, StepState>>({
    identity: "active",
    address: "pending",
    aml: "pending",
    documents: "pending",
    review: "pending",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isComplete, setIsComplete] = useState(false);

  // Form data state
  const [identity, setIdentity] = useState<Partial<PersonalIdentityForm>>({});
  const [address, setAddress] = useState<Partial<AddressForm>>({});
  const [uploadedFiles, setUploadedFiles] = useState<Record<string, UploadedFile | null>>({});
  const [consents, setConsents] = useState<ConsentForm>({
    amlScreening: null,
    dataProcessing: null,
    marketingComms: null,
  });

  const advanceStep = () => {
    const step = WIZARD_STEPS[currentStep];
    setStepStates((prev) => ({ ...prev, [step.id]: "completed" }));

    if (currentStep < WIZARD_STEPS.length - 1) {
      const next = WIZARD_STEPS[currentStep + 1];
      setStepStates((prev) => ({ ...prev, [next.id]: "active" }));
      setCurrentStep((prev) => prev + 1);
    }
  };

  const handleNext = () => {
    // Trigger form submit for form-based steps
    const formIds: Record<number, string> = {
      0: "step-identity-form",
      1: "step-address-form",
    };
    const formId = formIds[currentStep];
    if (formId) {
      document.getElementById(formId)?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    } else {
      advanceStep();
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      const prev = WIZARD_STEPS[currentStep - 1];
      const curr = WIZARD_STEPS[currentStep];
      setStepStates((s) => ({
        ...s,
        [curr.id]: "pending",
        [prev.id]: "active",
      }));
      setCurrentStep((p) => p - 1);
    }
  };

  const handleSubmit = async () => {
    if (!consents.amlScreening || !consents.dataProcessing) return;
    setIsSubmitting(true);
    // TODO: call api/kyc endpoint
    await new Promise((r) => setTimeout(r, 1500));
    setIsSubmitting(false);
    setIsComplete(true);
  };

  const canAdvance = (): boolean => {
    if (currentStep === 4) {
      return consents.amlScreening === "accepted" && consents.dataProcessing === "accepted";
    }
    return true;
  };

  if (isComplete) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 px-6" aria-live="polite">
        <CheckCircle2 size={64} className="text-[#10b981]" aria-hidden="true" />
        <h2 className="text-2xl font-bold text-[oklch(95%_0_0)]">Application Submitted</h2>
        <p className="text-sm text-[oklch(65%_0_0)] text-center max-w-md">
          Your KYC application has been received. You will be notified within 1–2 business days. Reference: KYC-
          {Math.random().toString(36).slice(2, 10).toUpperCase()}
        </p>
        <StatusBadge status="PENDING" showIcon showLabel />
      </div>
    );
  }

  return (
    <div className="min-h-screen px-4 py-8 md:px-8 max-w-2xl mx-auto" style={{ background: "oklch(10% 0 0)" }}>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-[oklch(95%_0_0)] mb-1">KYC Onboarding</h1>
        <p className="text-xs text-[oklch(45%_0_0)]">Complete all steps to open your BANXE account</p>
      </div>

      <StepWizard
        steps={WIZARD_STEPS}
        currentStep={currentStep}
        stepStates={stepStates}
        onNext={handleNext}
        onBack={handleBack}
        onSubmit={handleSubmit}
        isSubmitting={isSubmitting}
        canAdvance={canAdvance()}
        submitLabel="Submit Application"
      >
        {currentStep === 0 && (
          <PersonalIdentityStep
            defaultValues={identity}
            onComplete={(data) => {
              setIdentity(data);
              advanceStep();
            }}
          />
        )}
        {currentStep === 1 && (
          <AddressStep
            defaultValues={address}
            onComplete={(data) => {
              setAddress(data);
              advanceStep();
            }}
          />
        )}
        {currentStep === 2 && <AMLScreeningStep autoStart />}
        {currentStep === 3 && (
          <DocumentUploadStep
            files={uploadedFiles}
            onFilesChange={(key, file) => setUploadedFiles((prev) => ({ ...prev, [key]: file }))}
          />
        )}
        {currentStep === 4 && (
          <ReviewStep
            identity={identity}
            address={address}
            consents={consents}
            onConsentChange={(key, value) => setConsents((prev) => ({ ...prev, [key]: value }) as ConsentForm)}
          />
        )}
      </StepWizard>
    </div>
  );
}

export default KYCWizard;
