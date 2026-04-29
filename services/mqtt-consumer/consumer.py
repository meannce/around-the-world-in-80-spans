import os, json, logging, time
import paho.mqtt.client as mqtt
import requests
from opentelemetry import trace, propagate
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.instrumentation.requests import RequestsInstrumentor

log = logging.getLogger("mqtt-consumer")
logging.basicConfig(level=logging.INFO)

resource = Resource.create({SERVICE_NAME: os.environ.get("OTEL_SERVICE_NAME", "mqtt-consumer")})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"))
))
trace.set_tracer_provider(provider)
RequestsInstrumentor().instrument()

tracer    = trace.get_tracer("mqtt-consumer")
prop      = TraceContextTextMapPropagator()
entry_url = os.environ.get("ENTRY_URL", "http://entry:5000/finalize")

def on_connect(client, userdata, flags, reason_code, properties):
    log.info(f"MQTT connected: {reason_code}")
    client.subscribe("journey/complete")

def on_message(client, userdata, msg):
    journey = json.loads(msg.payload.decode())
    journey["stops"] = journey.get("stops", []) + ["mqtt-consumer"]
    journey["hop"]   = journey.get("hop", 0) + 1

    # extract traceparent from MQTT 5 user properties if present
    carrier = {}
    if msg.properties and hasattr(msg.properties, 'UserProperty'):
        for key, val in (msg.properties.UserProperty or []):
            carrier[key] = val

    ctx = prop.extract(carrier)

    with tracer.start_as_current_span("mqtt-consumer.receive", context=ctx) as span:
        span.set_attribute("messaging.system", "mqtt")
        span.set_attribute("messaging.destination", "journey/complete")
        log.info(f"MQTT journey complete: {journey['journey_id']}")

        headers = {"Content-Type": "application/json"}
        prop.inject(headers)

        try:
            requests.post(entry_url, json=journey, headers=headers, timeout=10)
            log.info(f"Journey {journey['journey_id']} finalized. Total stops: {len(journey['stops'])}")
        except Exception as e:
            log.warning(f"finalize error: {e}")


def main():
    host = os.environ.get("MQTT_HOST", "mosquitto")
    port = int(os.environ.get("MQTT_PORT", "1883"))

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    for _ in range(30):
        try:
            client.connect(host, port, 60)
            break
        except Exception:
            time.sleep(2)

    log.info("mqtt-consumer ready")
    client.loop_forever()

if __name__ == "__main__":
    main()
