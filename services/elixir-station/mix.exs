defmodule Station.MixProject do
  use Mix.Project

  def project do
    [
      app: :station,
      version: "0.1.0",
      elixir: "~> 1.16",
      start_permanent: Mix.env() == :prod,
      deps: deps()
    ]
  end

  def application do
    [extra_applications: [:logger], mod: {Station.Application, []}]
  end

  defp deps do
    [
      {:plug_cowboy, "~> 2.7"},
      {:jason, "~> 1.4"},
      {:amqp, "~> 3.3"},
      {:opentelemetry, "~> 1.4"},
      {:opentelemetry_api, "~> 1.4"},
      {:opentelemetry_exporter, "~> 1.7"},
      {:httpoison, "~> 2.0"}
    ]
  end
end
