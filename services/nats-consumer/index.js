const { NodeSDK } = require('@opentelemetry/sdk-node');
const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-grpc');
const { Resource } = require('@opentelemetry/resources');
const { SEMRESATTRS_SERVICE_NAME } = require('@opentelemetry/semantic-conventions');
const { trace, propagation, context } = require('@opentelemetry/api');

const exporter = new OTLPTraceExporter({
  url: process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'grpc://otel-collector:4317',
});
const sdk = new NodeSDK({
  resource: new Resource({ [SEMRESATTRS_SERVICE_NAME]: process.env.OTEL_SERVICE_NAME || 'nats-consumer' }),
  traceExporter: exporter,
});
sdk.start();

const { connect, StringCodec } = require('nats');
const mqtt = require('mqtt');

const sc = StringCodec();

async function main() {
  const natsUrl  = process.env.NATS_URL  || 'nats://nats:4222';
  const mqttHost = process.env.MQTT_HOST || 'mosquitto';
  const mqttPort = parseInt(process.env.MQTT_PORT || '1883', 10);

  const nc = await connect({ servers: natsUrl });
  const sub = nc.subscribe('journey');
  console.log('nats-consumer ready, subscribed to "journey"');

  const mqttClient = mqtt.connect(`mqtt://${mqttHost}:${mqttPort}`);

  for await (const msg of sub) {
    const journey = JSON.parse(sc.decode(msg.data));
    journey.stops = [...(journey.stops || []), 'nats-consumer'];
    journey.hop = (journey.hop || 0) + 1;

    // Extract trace context from NATS message headers
    const carrier = {};
    if (msg.headers) {
      for (const [k, v] of msg.headers) {
        carrier[k] = v;
      }
    }

    const parentCtx = propagation.extract(context.active(), carrier);
    const tracer = trace.getTracer('nats-consumer');
    const span = tracer.startSpan('nats-consumer.receive', {
      kind: trace.SpanKind?.CONSUMER ?? 3,
    }, parentCtx);

    const activeCtx = trace.setSpan(parentCtx, span);

    // inject into outgoing MQTT user-properties header
    const outCarrier = {};
    propagation.inject(activeCtx, outCarrier);

    const mqttProps = outCarrier.traceparent
      ? { properties: { userProperties: { traceparent: outCarrier.traceparent } } }
      : {};

    mqttClient.publish('journey/complete', JSON.stringify(journey), mqttProps);
    console.log(`nats-consumer: published to MQTT for journey ${journey.journey_id}`);

    span.end();
  }
}

main().catch(console.error);
process.on('SIGTERM', () => sdk.shutdown());
