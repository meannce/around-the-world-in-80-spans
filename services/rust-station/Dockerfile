FROM rust:alpine AS chef
RUN apk add --no-cache musl-dev pkgconfig openssl-dev && \
    cargo install cargo-chef
WORKDIR /app

FROM chef AS planner
COPY . .
RUN cargo chef prepare --recipe-path recipe.json

FROM chef AS builder
COPY --from=planner /app/recipe.json recipe.json
RUN cargo chef cook --release --recipe-path recipe.json
COPY . .
RUN cargo build --release

FROM alpine:3.20
RUN apk add --no-cache libgcc
WORKDIR /app
COPY --from=builder /app/target/release/rust-station .
CMD ["./rust-station"]
