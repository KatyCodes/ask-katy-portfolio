# Recruiter Question Handoff

## Recommended interaction

1. The assistant answers from Katy's approved professional facts when possible.
2. If the answer is unavailable, it says so without inventing information.
3. The recruiter may choose **Send this question to Katy**.
4. The backend validates and rate-limits the request, then sends Katy an SMS notification containing the application ID and question.
5. The page confirms only after the SMS provider accepts the message.

The assistant must not claim that Katy will answer immediately. A one-way SMS notification does not provide a response channel to the recruiter.

## Required safeguards

- Explicit recruiter action before sending
- Per-session, per-IP, and daily global limits
- Maximum question length and plain-text normalization
- No raw access token, IP address, hidden prompt, or private context in the SMS
- Provider credentials and Katy's phone number stored only as backend secrets
- Generic browser errors that do not reveal the phone number or provider
- Kill switch for the handoff endpoint
- Operational logging without full question text by default

## Decision before implementation

Choose whether the handoff is only a private alert to Katy or whether recruiters may provide an email address for a response. Collecting contact information requires a clear consent message, retention policy, and deletion process.
