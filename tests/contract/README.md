# Go parity fixtures

`fixtures/*.json` were recorded against Go KARR `161e379` (tag `go-final-0.2.2`)
running on a real PostgreSQL with the integration suite's mock BONNIE, by the
test in `capture_fixtures_go_test.go.txt` (kept as text; it is Go and needs the
Go tree to run). Each file holds one request and the exact Go response.

The contract tests replay the requests against the Python service and compare
status and body shape. Volatile fields (ids, timestamps, tokens) are
normalised. Every allowed difference is annotated with the K-D id from the
plan; a difference without a K-D id is a porting bug.

## Replay (K7)

`tests/integration/test_contract_replay.py` replays every fixture in order
against the Python app with the Go mock BONNIE reproduced in respx, substitutes
the identifiers created along the way, and compares the status and the body
shape (keys and value types). `DEVIATIONS` in that file lists every fixture
allowed to differ with its K-D id; the plan's §6 table explains each id. The
replay found one Go defect the inventory had missed: the environment list
dropped `project_id`, `env`, `mounts` and `command` (K-D25).

`tests/integration/test_e2e_fake_bonnie.py` is the §10.3 scenario: provision,
install script, register, first poll, environment lifecycle with a streamed
log, a container killed behind KARR's back, and the guarded agent delete.
