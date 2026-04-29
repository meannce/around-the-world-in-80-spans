import os, json, asyncio, logging
import pika
import nats
from opentelemetry import trace, propagate
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

log = logging.getLogger("rabbit-consumer")
logging.basicConfig(level=logging.INFO)

# ── OTel ─────────────────────────────────────────────────────────────────────
resource = Resource.create({SERVICE_NAME: os.environ.get("OTEL_SERVICE_NAME", "rabbit-consumer")})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"))
))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("rabbit-consumer")
propagator = TraceContextTextMapPropagator()

NATS_URL    = os.environ.get("NATS_URL", "nats://nats:4222")
RABBIT_URL  = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")

def callback(ch, method, properties, body):
    journey = json.loads(body)
    journey["stops"] = journey.get("stops", []) + ["rabbit-consumer"]
    journey["hop"]   = journey.get("hop", 0) + 1

    # extract trace context from AMQP headers
    headers = {}
    if properties.headers:
        for k, v in properties.headers.items():
            headers[k] = v.decode() if isinstance(v, bytes) else str(v)

    ctx = propagator.extract(headers)

    with tracer.start_as_current_span("rabbit-consumer.receive", context=ctx) as span:
        span.set_attribute("messaging.system", "rabbitmq")
        span.set_attribute("messaging.destination", "journey")
        log.info(f"rabbit-consumer: {journey['journey_id']}")

        # forward via NATS (sync call to async)
        try:
            asyncio.run(publish_nats(journey, span))
        except Exception as e:
            log.warning(f"NATS publish error: {e}")

    ch.basic_ack(delivery_tag=method.delivery_tag)


async def publish_nats(journey: dict, parent_span):
    nc = await nats.connect(NATS_URL)
    headers_out = {}
    propagator.inject(headers_out)  # inject current span context

    await nc.publish(
        "journey",
        json.dumps(journey).encode(),
        headers={"traceparent": headers_out.get("traceparent", "")} if headers_out.get("traceparent") else None,
    )
    await nc.drain()
    log.info("published to NATS")


def main():
    import time
    params = pika.URLParameters(RABBIT_URL)
    conn = None
    for _ in range(30):
        try:
            conn = pika.BlockingConnection(params)
            break
        except Exception:
            time.sleep(2)

    if conn is None:
        raise RuntimeError("Could not connect to RabbitMQ")

    ch = conn.channel()
    ch.queue_declare(queue="journey", durable=True)
    ch.basic_consume(queue="journey", on_message_callback=callback)
    log.info("rabbit-consumer ready")
    ch.start_consuming()


if __name__ == "__main__":
    main()
