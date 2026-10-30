# Security policy

## Supported version

Security fixes are applied to the latest release on the `main` branch.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do not open a public issue containing exploit details, private paths, proprietary reports, game files, credentials, or tokens.

## Local-only threat model

Recomp Observatory is designed to bind to `127.0.0.1` and rejects non-loopback host headers and cross-site writes. Do not expose it on `0.0.0.0`, forward its port to the internet, or place it behind a public reverse proxy.

The observer reads bounded report files and metadata from repositories selected by the local user. It does not execute target scripts, compilers, games, tests, or emulators. Custom artwork and workspace history remain under the ignored local `work/` directory.
