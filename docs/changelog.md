# Changelog

## 0.3.0

Python rewrite of the Go service (preserved at tag `go-final-0.2.2`). Same
routes, schema and SPA; the defects fixed are listed by K-D id in the FLAG
Python Rewrite Plan and summarised here as the service PRs land.

- K1: scaffold, admin bearer auth (K-D1), error envelope with 413/422 (K-D5,
  K-D19), CSP/HSTS headers (K-D15), CORS `max_age` (K-D14), non-root image with
  `HEALTHCHECK` (K-D16), Fernet token cipher (K-D12).
