# Stage 1: Build frontend
FROM node:22-alpine AS web-builder
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: Build Go binary
FROM golang:1.25-alpine AS go-builder
RUN apk add --no-cache gcc musl-dev
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
COPY --from=web-builder /app/web/dist ./web/dist
ARG VERSION=dev
ARG COMMIT=unknown
ARG BUILD_DATE=unknown
RUN CGO_ENABLED=0 go build -ldflags "\
  -X github.com/flag-ai/commons/version.Version=${VERSION} \
  -X github.com/flag-ai/commons/version.Commit=${COMMIT} \
  -X github.com/flag-ai/commons/version.Date=${BUILD_DATE}" \
  -o /karr ./cmd/karr

# Stage 3: Final image
FROM alpine:3.21
RUN apk add --no-cache ca-certificates tzdata
COPY --from=go-builder /karr /usr/local/bin/karr
COPY --from=go-builder /app/migrations /migrations
EXPOSE 8080
ENTRYPOINT ["karr"]
CMD ["serve"]
