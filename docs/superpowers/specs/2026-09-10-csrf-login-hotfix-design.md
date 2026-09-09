# CSRF login hotfix design

## Problem
The panel login form correctly emits a CSRF token, but `create_app()` defaults `SESSION_COOKIE_SECURE=True`. The production panel currently binds plain HTTP on port 80, so browsers can withhold the Secure session cookie on login POST, causing `The CSRF session token is missing.`

## Fix
Make cookie security explicitly controlled by `PANEL_COOKIE_SECURE`, defaulting to false for the current HTTP deployment. Keep HTTPS-ready behavior by allowing `PANEL_COOKIE_SECURE=1` to restore Secure cookies. Do not disable CSRF protection.

## Verification
Add a regression test that creates the app in non-testing mode without `PANEL_COOKIE_SECURE`, performs GET `/login`, extracts the CSRF token, and verifies POST `/login` over HTTP reaches form validation instead of returning HTTP 400. Add a second test proving `PANEL_COOKIE_SECURE=1` sets a Secure session cookie.
