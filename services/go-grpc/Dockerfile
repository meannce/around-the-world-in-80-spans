FROM golang:1.22-alpine AS builder
RUN apk add --no-cache protobuf protobuf-dev
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@latest \
 && go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
WORKDIR /app
COPY go.mod .
RUN go mod download || true
COPY . .
RUN mkdir -p pb && \
    protoc --go_out=pb --go_opt=paths=source_relative \
           --go-grpc_out=pb --go-grpc_opt=paths=source_relative \
           journey.proto
RUN go mod tidy && CGO_ENABLED=0 go build -o grpc-server .

FROM alpine:3.20
WORKDIR /app
COPY --from=builder /app/grpc-server .
CMD ["./grpc-server"]
