package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"

	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	pb "github.com/journey/go-grpc/pb"
)

type server struct {
	pb.UnimplementedJourneyServiceServer
}

func (s *server) PassThrough(ctx context.Context, req *pb.JourneyRequest) (*pb.JourneyResponse, error) {
	log.Printf("gRPC PassThrough: journey=%s hop=%d", req.JourneyId, req.Hop)
	stops := append(req.Stops, "go-grpc")
	return &pb.JourneyResponse{
		Status:      "passed",
		ProcessedBy: "go-grpc",
		Stops:       stops,
	}, nil
}

func initTracer() func(context.Context) error {
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		endpoint = "otel-collector:4317"
	}
	if len(endpoint) > 7 && endpoint[:7] == "http://" {
		endpoint = endpoint[7:]
	}

	conn, _ := grpc.NewClient(endpoint, grpc.WithTransportCredentials(insecure.NewCredentials()))
	exp, _ := otlptracegrpc.New(context.Background(), otlptracegrpc.WithGRPCConn(conn))

	svcName := os.Getenv("OTEL_SERVICE_NAME")
	if svcName == "" {
		svcName = "go-grpc"
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

func main() {
	shutdown := initTracer()
	defer shutdown(context.Background())

	lis, err := net.Listen("tcp", ":50051")
	if err != nil {
		log.Fatalf("listen: %v", err)
	}

	s := grpc.NewServer(
		grpc.StatsHandler(otelgrpc.NewServerHandler()),
	)
	pb.RegisterJourneyServiceServer(s, &server{})

	fmt.Println("go-grpc listening on :50051")
	if err := s.Serve(lis); err != nil {
		log.Fatalf("serve: %v", err)
	}
}
