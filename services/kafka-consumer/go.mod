module github.com/journey/kafka-consumer

go 1.23

require (
	github.com/IBM/sarama v1.43.2
	go.opentelemetry.io/otel v1.27.0
	go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc v1.27.0
	go.opentelemetry.io/otel/sdk v1.27.0
go.opentelemetry.io/otel/trace v1.27.0
	google.golang.org/grpc v1.64.0
)
