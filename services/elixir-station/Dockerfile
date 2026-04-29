FROM elixir:1.17-alpine
RUN apk add --no-cache build-base git
WORKDIR /app
COPY mix.exs .
RUN mix local.hex --force && mix local.rebar --force
RUN mix deps.get
COPY . .
RUN MIX_ENV=prod mix compile
ENV MIX_ENV=prod
CMD ["mix", "run", "--no-halt"]
