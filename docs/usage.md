# Using KARR

A walk through the first agent and environment. The API reference is
[api.md](api.md); the SPA does the same calls.

## 1. Sign in

Open KARR in a browser and enter the value of `KARR_ADMIN_TOKEN`. The token is
verified against `GET /api/v1/auth/check` and kept in the tab's `sessionStorage`
only; a rotated token sends you back to the form. Every API call below carries
`Authorization: Bearer <token>`.

## 2. Register a GPU host

**Install command (recommended).** On the Agents page, enter a label and
generate an install command. KARR creates a pending registration (visible under
*Pending Registrations*, expiring after `KARR_REGISTRATION_TTL`) and shows:

```
curl -fsSL https://karr.example.com/api/v1/install.sh?token=... | sudo bash -s --
```

Run it on the host. The script installs BONNIE as a systemd unit, then BONNIE
calls `POST /api/v1/agents/register` with the token; KARR claims the token and
creates the agent in one transaction. The agent shows `offline` until the
registry's next poll reaches it (about ten seconds).

**Manual.** `POST /api/v1/agents` with `name`, `url` (`http(s)://host:7777`) and
the BONNIE bearer `token`. Tokens are stored encrypted with `KARR_SECRET_KEY`.

The Dashboard shows each online agent's host, CPU, memory, disk and GPU
memory/utilisation bars, refreshed every ten seconds.

## 3. Create a project (optional)

Projects are labels for grouping environments. Deleting one leaves its
environments running without a project.

## 4. Create an environment

On the Environments page pick an agent, a name (unique per agent), an image,
optionally a project and the GPU flag. KARR writes the row as `creating`, asks
BONNIE to create the container, then marks it `stopped`. A BONNIE failure
leaves the row in `error` with the message on the row; remove it and retry.

State machine: `creating -> stopped <-> running`, `error` from any failed
operation. `Start` is offered for `stopped`, `Stop` for `running`, `Remove`
for `stopped` and `error`. Every destructive action asks for confirmation and
every failure is shown as a toast.

## 5. Logs

`Logs` on a running (or stopped) environment opens the container's log stream:
one server-sent event per line, keepalives every 15 s, `event: end` when the
container's stream closes, `event: error` with a message on failure. The viewer
keeps the last 5 000 lines, reconnects with backoff after a dropped connection
(marking the restart) and stops on end or error. At most 8 streams per agent and 3
per client are open at once (429 past that) and a stream ends after 4 hours;
reopen to continue.

## 6. Reconciliation

Every `KARR_RECONCILE_INTERVAL` seconds KARR lists the containers on each
online agent and updates environment status (`running`, `stopped`, or `error`
with "container missing"). A row left `creating` by a crash is adopted through
its container name after a 60 s grace, or marked `error` if nothing exists.
`/ready` reports the `reconciler` check as informational; it fails after three
missed passes.

## 7. Remove things

- **Environment**: removes the container, then the row. A container BONNIE no
  longer knows about can be removed once the reconciler marked it missing.
- **Agent**: refused (409) while environments reference it; `?force=true`
  removes their containers on BONNIE first, then the rows. If a container
  cannot be removed the rows stay and the call answers 409 naming them.
- **Registration**: cancelling a pending registration invalidates its install
  command.
