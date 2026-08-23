# Password reset capability

Users who have access to an account email address must be able to request a password-reset link.

Rules:
- A reset token expires 30 minutes after issuance.
- A reset token is single-use.
- Requesting reset must not reveal whether an email address exists.
- A successful reset invalidates other active reset tokens for the same user.

Acceptance:
- An expired token is rejected.
- A used token is rejected.
- A valid token changes the password exactly once.
