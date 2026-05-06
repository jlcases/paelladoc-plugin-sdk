# Next.js SaaS PRD

## Outcome

What user or business behavior must change?

## Routes

- New routes:
- Existing routes changed:
- Auth state:
- Empty/loading/error states:

## Acceptance Criteria

- Given a signed-out user, when they access the route, then auth behavior is explicit.
- Given a mobile viewport, when the primary flow is used, then no text overlaps.
- Given a failed server action, when the UI recovers, then the user sees the next action.

## Quality Gates

- `pnpm lint`
- `pnpm typecheck`
- `pnpm test`
- Playwright smoke for the primary route
