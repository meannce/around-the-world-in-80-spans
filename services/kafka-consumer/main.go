package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/IBM/sarama"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
	"go.opentelemetry.io/otel/trace"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type kafkaHeaderCarrier []sarama.RecordHeader

func (c kafkaHeaderCarrier) Get(key string) string {
	for _, h := range c {
		if string(h.Key) == key {
			return string(h.Value)
		}
	}
	return ""
}
func (c kafkaHeaderCarrier) Set(key, val string) {}
func (c kafkaHeaderCarrier) Keys() []string {
	keys := make([]string, len(c))
	for i, h := range c {
		keys[i] = string(h.Key)
	}
	return keys
}

type Journey struct {
	JourneyID string   `json:"journey_id"`
	StartedAt string   `json:"started_at"`
	Hop       int      `json:"hop"`
	Stops     []string `json:"stops"`
}

func initTracer() func(context.Context) error {
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		endpoint = "otel-collector:4317"
	}
	// strip http:// prefix if present
	if len(endpoint) > 7 && endpoint[:7] == "http://" {
		endpoint = endpoint[7:]
	}

	conn, err := grpc.NewClient(endpoint, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("grpc connect: %v", err)
	}

	exp, err := otlptracegrpc.New(context.Background(), otlptracegrpc.WithGRPCConn(conn))
	if err != nil {
		log.Fatalf("otlp exporter: %v", err)
	}

	svcName := os.Getenv("OTEL_SERVICE_NAME")
	if svcName == "" {
		svcName = "kafka-consumer"
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exp),
		sdktrace.WithResource(resource.NewWithAttributes(
			semconv.SchemaURL,
			semconv.ServiceName(svcName),
		)),
	)
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{}, propagation.Baggage{},
	))
	return tp.Shutdown
}

type handler struct {
	tracer   trace.Tracer
	nextStop string
}

func (h *handler) Setup(_ sarama.ConsumerGroupSession) error   { return nil }
func (h *handler) Cleanup(_ sarama.ConsumerGroupSession) error { return nil }

func (h *handler) ConsumeClaim(sess sarama.ConsumerGroupSession, claim sarama.ConsumerGroupClaim) error {
	for msg := range claim.Messages() {
		carrier := kafkaHeaderCarrier(msg.Headers)
		ctx := otel.GetTextMapPropagator().Extract(context.Background(), carrier)

		_, span := h.tracer.Start(ctx, "kafka-consumer.receive",
			trace.WithSpanKind(trace.SpanKindConsumer),
		)
		span.SetAttributes(
			semconv.MessagingSystem("kafka"),
			semconv.MessagingDestinationName("journey"),
		)

		var journey Journey
		if err := json.Unmarshal(msg.Value, &journey); err != nil {
			log.Printf("unmarshal: %v", err)
			span.End()
			sess.MarkMessage(msg, "")
			continue
		}

		journey.Hop++
		journey.Stops = append(journey.Stops, "kafka-consumer")
		log.Printf("consumed journey %s, forwarding to %s", journey.JourneyID, h.nextStop)

		if err := forward(ctx, h.nextStop, journey); err != nil {
			log.Printf("forward error: %v", err)
		}

		span.End()
		sess.MarkMessage(msg, "")
	}
	return nil
}

func forward(ctx context.Context, nextStop string, journey Journey) error {
	body, _ := json.Marshal(journey)
	req, _ := http.NewRequestWithContext(ctx, "POST", nextStop, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")

	carrier := make(map[string]string)
	otel.GetTextMapPropagator().Inject(ctx, propagation.MapCarrier(carrier))
	for k, v := range carrier {
		req.Header.Set(k, v)
	}

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return nil
}

func main() {
	shutdown := initTracer()
	defer shutdown(context.Background())

	tracer := otel.Tracer("kafka-consumer")

	brokers := os.Getenv("KAFKA_BOOTSTRAP_SERVERS")
	if brokers == "" {
		brokers = "kafka:9092"
	}
	nextStop := os.Getenv("NEXT_STOP")
	if nextStop == "" {
		nextStop = "http://node-station:3000/journey"
	}

	cfg := sarama.NewConfig()
	cfg.Version = sarama.V3_6_0_0
	cfg.Consumer.Offsets.Initial = sarama.OffsetNewest

	var cg sarama.ConsumerGroup
	var err error
	for i := 0; i < 30; i++ {
		cg, err = sarama.NewConsumerGroup([]string{brokers}, "journey-group", cfg)
		if err == nil {
			break
		}
		log.Printf("waiting for kafka... (%v)", err)
		time.Sleep(2 * time.Second)
	}
	if err != nil {
		log.Fatalf("consumer group: %v", err)
	}
	defer cg.Close()

	h := &handler{tracer: tracer, nextStop: nextStop}
	fmt.Println("kafka-consumer ready, listening on topic 'journey'")

	for {
		if err := cg.Consume(context.Background(), []string{"journey"}, h); err != nil {
			log.Printf("consume error: %v", err)
			time.Sleep(time.Second)
		}
	}
}
