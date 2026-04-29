defmodule Station.Application do
  use Application

  def start(_type, _args) do
    children = [
      {Plug.Cowboy, scheme: :http, plug: Station.Router, options: [port: 4000]}
    ]
    Supervisor.start_link(children, strategy: :one_for_one, name: Station.Supervisor)
  end
end

defmodule Station.Router do
  use Plug.Router

  plug(Plug.Logger)
  plug(:match)
  plug(Plug.Parsers, parsers: [:json], pass: ["application/json"], json_decoder: Jason)
  plug(:dispatch)

  post "/journey" do
    journey = conn.body_params
    stops   = (journey["stops"] || []) ++ ["elixir-station"]
    hop     = (journey["hop"] || 0) + 1
    journey = Map.merge(journey, %{"stops" => stops, "hop" => hop})

    traceparent = Plug.Conn.get_req_header(conn, "traceparent") |> List.first()

    Task.start(fn ->
      publish_via_http_api(journey, traceparent)
    end)

    conn
    |> put_resp_content_type("application/json")
    |> send_resp(200, Jason.encode!(%{status: "passed", service: "elixir-station", stops: stops}))
  end

  get "/health" do
    conn
    |> put_resp_content_type("application/json")
    |> send_resp(200, ~s({"status":"ok"}))
  end

  match _ do
    send_resp(conn, 404, "not found")
  end

  defp publish_via_http_api(journey, traceparent) do
    # Publish to RabbitMQ via HTTP management API — avoids native AMQP lib
    rabbit_host = System.get_env("RABBITMQ_HOST", "rabbitmq")
    api_url = "http://#{rabbit_host}:15672/api/exchanges/%2F//publish"
    auth    = Base.encode64("guest:guest")

    headers_map = if traceparent, do: %{"traceparent" => traceparent}, else: %{}

    body = Jason.encode!(%{
      properties: %{content_type: "application/json", headers: headers_map},
      routing_key: "journey",
      payload: Jason.encode!(journey),
      payload_encoding: "string"
    })

    case HTTPoison.post(api_url, body, [
      {"Content-Type", "application/json"},
      {"Authorization", "Basic #{auth}"}
    ]) do
      {:ok, %{status_code: 200}} -> IO.puts("elixir-station: published to RabbitMQ")
      {:ok, r}                   -> IO.puts("elixir-station: RabbitMQ API #{r.status_code}")
      {:error, e}                -> IO.puts("elixir-station: RabbitMQ error #{inspect(e)}")
    end
  end
end
