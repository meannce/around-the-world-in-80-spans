FROM elixir:1.17-alpine AS builder
RUN apk add --no-cache build-base git
WORKDIR /app
COPY mix.exs .
RUN mix local.hex --force && mix local.rebar --force
RUN mix deps.get
COPY . .
RUN MIX_ENV=prod mix release

FROM alpine:3.20
RUN apk add --no-cache libstdc++ openssl ncurses
WORKDIR /app
COPY --from=builder /app/_build/prod/rel/station .
ENV MIX_ENV=prod
CMD ["./bin/station", "start"]
