# Go parity fixtures

`fixtures/*.json` were recorded against Go KARR `161e379` (tag `go-final-0.2.2`)
running on a real PostgreSQL with the integration suite's mock BONNIE, by the
test in `capture_fixtures_go_test.go.txt` (kept as text; it is Go and needs the
Go tree to run). Each file holds one request and the exact Go response.

The contract tests replay the requests against the Python service and compare
status and body shape. Volatile fields (ids, timestamps, tokens) are
normalised. Every allowed difference is annotated with the K-D id from the
plan; a difference without a K-D id is a porting bug.
