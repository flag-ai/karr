.PHONY: dev test lint sqlc build docker

# Development
dev:
	docker compose up -d postgres
	@echo "Postgres started. Run 'go run ./cmd/karr serve' and 'cd web && npm run dev'"

# Testing
test:
	go test -race -coverprofile=coverage.out ./...
	@echo "Coverage:"
	@go tool cover -func=coverage.out | tail -1

test-integration:
	go test -race -tags integration ./tests/...

# Code quality
lint:
	golangci-lint run

security:
	gosec ./...

# Code generation
sqlc:
	sqlc generate

# Build
build:
	go build -o karr ./cmd/karr

build-web:
	cd web && npm ci && npm run build

# Docker
docker:
	docker compose build

docker-up:
	docker compose up

docker-down:
	docker compose down
