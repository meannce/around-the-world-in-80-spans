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

    rabbitmq_url = System.get_env("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")

    # Extract traceparent from incoming headers to propagate
    traceparent = Plug.Conn.get_req_header(conn, "traceparent") |> List.first()

    Task.start(fn ->
      publish_to_rabbit(rabbitmq_url, journey, traceparent)
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

  defp publish_to_rabbit(url, journey, traceparent) do
    case AMQP.Connection.open(url) do
      {:ok, conn} ->
        {:ok, channel} = AMQP.Channel.open(conn)
        AMQP.Queue.declare(channel, "journey", durable: true)

        headers = if traceparent, do: [{"traceparent", :longstr, traceparent}], else: []

        AMQP.Basic.publish(
          channel,
          "",
          "journey",
          Jason.encode!(journey),
          content_type: "application/json",
          headers: headers
        )

        AMQP.Connection.close(conn)

      {:error, reason} ->
        IO.puts("RabbitMQ publish error: #{inspect(reason)}")
    end
  end
end
