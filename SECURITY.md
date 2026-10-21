# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security vulnerability. Report it
privately to the repository owner through GitHub's private vulnerability
reporting, including the affected version, reproduction steps, and impact.

Until a fix is released, avoid downloading executables from untrusted URLs and
keep FFmpeg installation enabled only when its SHA-256 verification succeeds.

## Scope

Security reports covering URL handling, command execution, downloaded binaries,
credential access, state-file handling, and path traversal are welcome.

## Download state and filesystem boundaries

Saved task paths are untrusted. Resume, queue processing and deletion validate
all media and sidecar paths against the current configuration before use.
Temporary media must be immediate children of `CONFIG_DIR/tmp`; final files
must be immediate children of the configured download directory. Traversal,
file symlinks, hard links and non-regular files are rejected. Invalid tasks are
ignored and logged, without deleting their referenced files. If you change the
download directory, restore the previous setting to resume its pending tasks.

The app does not run with elevated privileges. Keep its configuration and
download directories writable only by trusted users. Validation cannot protect
against another process with the same permissions replacing files concurrently.

## Dependency and workflow verification

`uv.lock` resolves runtime, development and build dependencies across supported
Python versions. CI installs the hash-checked, wheel-only exports in
`requirements/ci.txt` and `requirements/release.txt`. The checked-out project is
built separately with the locked backend and without build isolation, so the
build cannot silently resolve additional backend dependencies.

After intentionally updating dependencies with `uv lock`, regenerate both:

```sh
uv export --locked --all-extras --group build --no-emit-project --output-file requirements/ci.txt
uv export --locked --only-group build --no-emit-project --output-file requirements/release.txt
```

GitHub Actions use full commit hashes. Review upstream changes before updating
those hashes.

## Protocol and executable permission decisions

HTTP download support is intentional for compatibility. The CLI warns when a
download stream uses HTTP. Prefer HTTPS: HTTP provides no confidentiality or
protection against a network attacker changing the downloaded bytes. FTP is
explicitly rejected; its string in the URL blocklist is not an FTP connection.

The verified FFmpeg binary uses mode `0755` on Unix so it can execute. Only the
owner can write the binary; it has no setuid/setgid or world-write permissions.
The install directory must remain under the user's control.
