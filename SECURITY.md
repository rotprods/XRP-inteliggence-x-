# Security Policy

## Current security posture

This alpha release is a read-only market-intelligence system. It must not receive exchange trading permissions or custody credentials.

## Secret handling

- Load secrets only from environment variables or an approved secret manager.
- Never write secrets to logs, fixtures, screenshots, Drive documents or error payloads.
- Use separate keys per environment and provider.
- Restrict keys by IP where supported.
- Rotate exposed or suspicious keys immediately.

## Provider safety

- Enforce HTTPS.
- Apply strict timeouts and response-size limits.
- Validate content type and schema.
- Reject timestamps too far in the future.
- Treat third-party text/news as untrusted content.
- Do not follow arbitrary redirects to private-network addresses.

## Reporting

Record security findings privately with reproduction steps, affected version and severity. Do not publish credentials or active exploit details.
