# ARCHITECTURE-16: AI-Driven Design System

> BANXE EMI Stack | Feature 16 | Open-Source Design Infrastructure

## Overview

This feature implements a complete AI-driven design system for BANXE using open-source and low-cost tools: Google Stitch (AI prototyping), Ruflo (design-to-code), and OpenClaw (open-source design system framework).

## Architecture Diagram

```
+------------------+     +----------------+     +------------------+
|  Google Stitch   |---->|  Design Tokens |---->|   Component Lib  |
|  (AI Prototype)  |     |  (JSON/CSS)    |     |   (React/TSX)    |
+------------------+     +----------------+     +------------------+
        |                        |                       |
        v                        v                       v
+------------------+     +----------------+     +------------------+
|     Ruflo        |     |   OpenClaw     |     |  BANXE Modules   |
| (Design-to-Code) |     | (Design Sys)   |     |  Integration     |
+------------------+     +----------------+     +------------------+
```

## Components

### 1. Design Token System (`src/design-system/tokens/`)
- `colors.json` - BANXE brand palette + semantic tokens
- `typography.json` - Font scales, weights, line-heights
- `spacing.json` - 4px grid system
- `shadows.json` - Elevation levels
- `tokens.css` - Generated CSS custom properties

### 2. Component Library (`src/design-system/components/`)
- `AlertPanel.tsx` - Critical/warning/info alerts with severity accent
- `Sidebar.tsx` - Collapsible navigation (64px/240px)
- `StepWizard.tsx` - Multi-step KYC wizard with progress
- `ConsentToggle.tsx` - WCAG-compliant toggle switches
- `AuditTrail.tsx` - Monospace timestamp log display

### 3. Module-Specific UI

#### Dashboard (`src/modules/dashboard/DashboardPage.tsx`)
- Widget grid layout
- Real-time data cards
- Chart containers

#### AML Monitor (`src/modules/aml/AMLMonitor.tsx`)
- Alert table with severity system
- Detail slide-out panel
- Actions: Escalate, Assign, Close

#### KYC Wizard (`src/modules/kyc/KYCWizard.tsx`)
- 5-step flow: Identity > Address > Pre-screening > Documents > Review
- Progress bar with step indicators
- Form validation per step
- API integration for submission

## Design Principles

1. **Token-First**: All visual values from design tokens
2. **WCAG AA Compliant**: Contrast ratios, focus states, aria labels
3. **Dark Mode**: Full dark theme via token switching
4. **Responsive**: Mobile-first, single column below 768px
5. **Open-Source**: No proprietary design tool dependencies

## Tech Stack

| Tool | Purpose | Cost |
|------|---------|------|
| Google Stitch | AI prototype generation | Free |
| Ruflo | Design-to-code conversion | Free/OSS |
| OpenClaw | Design system framework | Free/OSS |
| Lucide React | Icon library | Free/OSS |
| Tailwind CSS | Utility classes | Free/OSS |
| Storybook | Component documentation | Free/OSS |

## File Structure

```
src/
  design-system/
    tokens/
      colors.json
      typography.json
      spacing.json
      tokens.css
    components/
      AlertPanel.tsx
      Sidebar.tsx
      StepWizard.tsx
      ConsentToggle.tsx
      AuditTrail.tsx
  modules/
    dashboard/
      DashboardPage.tsx
    aml/
      AMLMonitor.tsx
    kyc/
      KYCWizard.tsx
docs/
  ARCHITECTURE-16-AI-DESIGN-SYSTEM.md
  ai-design-monitor.md
tests/
  design-system/
    (10+ test files, 60+ tests)
```

## Testing Strategy

- Token validation: all values mapped in tokens.css
- Contrast ratios pass WCAG AA for all text/background
- Components render with token values only
- Buttons use equal-weight styling
- Tables use tabular-nums
- Dark mode coverage for all components
- KYC wizard completes all 5 steps

## Integration Points

- **Prompt 15** (Design-to-Code Pipeline): Ruflo receives Penpot exports
- **Prompt 14** (Agent Routing): UI components for agent status display
- **Prompt 13** (UIUX Starter Kit): Extends base component library

---

*Ticket: IL-ADDS-01 | Prompt: 16*
