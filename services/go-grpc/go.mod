module github.com/journey/go-grpc

go 1.24

require (
	go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc v0.52.0
	go.opentelemetry.io/otel v1.27.0
	go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc v1.27.0
	go.opentelemetry.io/otel/sdk v1.27.0
go.opentelemetry.io/otel/trace v1.27.0
	google.golang.org/grpc v1.64.0
	google.golang.org/protobuf v1.34.2
)
