# Fixpoint demo video

## Candidate submission recording

- Source file: `Recording 2026-09-14 005905.mp4`
- Duration: **2:49**
- Source size: **154,074,631 bytes**
- Current location: local-only, outside the repository
- Hosting status: **uploaded**

The binary is intentionally not committed to git. The local recording remains the high-resolution
backup source.

Public video URL: [Fixpoint multi-app agent demo](https://youtu.be/0u5WcobheGo)

## What the video demonstrates

Fixpoint is an autonomous customer-exception agent that does consequential cross-application
work and then proves the outcome instead of merely claiming success.

The project connects five external applications:

- Gmail
- Stripe
- HubSpot
- Slack
- Google Drive

The expected agent behavior is:

1. Accept one refund or exception request.
2. Inspect evidence across billing, CRM, inbox, chat, and policy records.
3. Branch when information is missing or contradictory.
4. Take only permitted actions inside the safety envelope.
5. Request human approval before irreversible financial action.
6. Verify the result against real provider state.
7. Recover cleanly from failures instead of claiming unverified success.

## Suggested reviewer checklist

While watching, confirm that the recording shows:

- A single understandable customer request entering the system.
- Distinct actions across at least three external applications.
- Stateful behavior carried across steps, not three disconnected API calls.
- A visible approval or refusal where money or policy is involved.
- An independently verified outcome.
- An evaluation result, repeated-run behavior, or other measurable reliability evidence.
- A complete beginning, middle, and end within approximately two minutes.

## Hosting checklist

1. Confirm that the uploaded video plays from start to finish.
2. Verify that captions, audio, and text remain legible after platform compression.
3. The public URL is now wired into `README.md`, `SUBMISSION.md`, and this file.
4. Add that same URL to the official hackathon submission form.
5. Keep the local 147 MB source file for backup; do not commit it to the repository.
