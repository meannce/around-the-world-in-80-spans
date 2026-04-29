require 'opentelemetry/sdk'
require 'opentelemetry/exporter/otlp'
require 'opentelemetry/instrumentation/sinatra'
require 'sinatra/base'
require 'faraday'
require 'json'

OpenTelemetry::SDK.configure do |c|
  c.service_name = ENV.fetch('OTEL_SERVICE_NAME', 'ruby-station')
  c.use 'OpenTelemetry::Instrumentation::Sinatra'
c.add_span_processor(
    OpenTelemetry::SDK::Trace::Export::BatchSpanProcessor.new(
      OpenTelemetry::Exporter::OTLP::Exporter.new(
        endpoint: ENV.fetch('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://otel-collector:4317')
      )
    )
  )
end

class Station < Sinatra::Base
  set :bind, '0.0.0.0'
  set :port, 4567

  post '/journey' do
    content_type :json
    journey = JSON.parse(request.body.read)
    journey['stops'] ||= []
    journey['stops'] << 'ruby-station'
    journey['hop'] = (journey['hop'] || 0) + 1

    next_stop = ENV.fetch('NEXT_STOP', 'http://php-station:8000/journey')

    begin
      conn = Faraday.new(url: next_stop) do |f|
        f.adapter Faraday.default_adapter
      end
      headers = { 'Content-Type' => 'application/json' }
      # propagate trace context
      OpenTelemetry.propagation.inject(headers)
      conn.post('', journey.to_json, headers)
    rescue => e
      warn "forward error: #{e.message}"
    end

    journey.to_json
  end

  get '/health' do
    '{"status":"ok"}'
  end
end

Station.run!
