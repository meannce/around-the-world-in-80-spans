FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod .
RUN go mod download || true
COPY . .
RUN go mod tidy && CGO_ENABLED=0 go build -o consumer .

FROM alpine:3.20
WORKDIR /app
COPY --from=builder /app/consumer .
CMD ["./consumer"]
