# ADR-021: Conversation-first AI workbench

## Status

Accepted

## Context

Pair Programmer exposed BEAST's model route, context, crystal reuse, execution
state, and SourcePlan controls, but those controls dominated the narrow editor
dock. Responses were difficult to scan, the prompt was undersized, and the
conversation competed with persistent workspace chrome. The capability was
present without providing a comfortable daily-driver coding flow.

## Options considered

| Option | Benefits | Costs |
|---|---|---|
| Keep the telemetry-first panel | Maximum operational state is always visible | Conversation and prompt remain cramped; weak task hierarchy |
| Move AI to a separate full-page route | Abundant room for chat and diagnostics | Breaks editor continuity and makes contextual edits slower |
| Progressive-disclosure editor dock with Focus mode | Keeps code and conversation together; lets users choose density | Requires two responsive layouts and carefully preserved state |

## Decision

Pair Programmer uses a conversation-first dock with a persistent Focus mode.

- Ask, Edit, and Agent are explicit intent modes with mode-specific guidance.
- The active conversation and prompt are the primary visual hierarchy.
- Context, crystal reuse, and run telemetry remain adjacent but collapse when
  they are not needed.
- Assistant output renders readable paragraphs, lists, inline code, and fenced
  code while escaping untrusted model content.
- Edit and Agent token streams remain internal until Action IR is compiled;
  the conversation receives a human-readable, file-by-file proposal instead
  of model control JSON.
- If an intermediate SourcePlan event is missed, the client recovers the plan
  from the terminal session event. Interrupted persisted messages are closed
  and marked recoverable rather than being restored as permanently running.
- Focus mode hides the explorer and redundant workspace headers, enlarging the
  editor and conversation without navigating away or losing state.
- The active model, context scope, crystal-reuse status, and governed
  SourcePlan handoff remain visible at the point of action.
- Keyboard submission, Escape-to-exit Focus, pressed states, native details,
  and labelled controls preserve keyboard and assistive-technology access.

## Trade-offs

- The compact dock intentionally reveals less telemetry until the user opens
  Context or Run details.
- Focus mode temporarily hides workspace summary chrome, so persistent editor
  breadcrumbs and status remain important for orientation.
- Rich model output is deliberately limited to a small safe formatting subset;
  arbitrary model-supplied HTML is not rendered.

## Consequences

- Normal mode supports quick contextual requests alongside the explorer.
- Focus mode provides a substantially taller conversation and composer while
  preserving live editor context.
- Crystallised compute reuse and governed review remain first-class BEAST
  differentiators instead of becoming disconnected diagnostics.
- Visual regression coverage now exercises populated normal and Focus states,
  including overflow, typography, context disclosure, and work-area geometry.
- Behavioral parity coverage simulates Action IR streaming, compilation, and
  completion and requires a `ready-to-review` proposal with no leaked JSON.
