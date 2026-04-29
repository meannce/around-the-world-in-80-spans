require('./tracing');

const express = require('express');
const axios = require('axios');
const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');
const path = require('path');
const { context, propagation, trace } = require('@opentelemetry/api');

const app = express();
app.use(express.json());

const nextStop = process.env.NEXT_STOP || 'http://ruby-station:4567/journey';
const grpcAddr = process.env.GO_GRPC_ADDR || 'go-grpc:50051';

// Load gRPC proto (we copy the proto file into the image)
const pkgDef = protoLoader.loadSync(path.join(__dirname, 'journey.proto'), {
  keepCase: true, longs: String, enums: String, defaults: true, oneofs: true,
});
const proto = grpc.loadPackageDefinition(pkgDef).journey;
const grpcClient = new proto.JourneyService(grpcAddr, grpc.credentials.createInsecure());

app.post('/journey', async (req, res) => {
  const journey = req.body;
  journey.stops = journey.stops || [];
  journey.stops.push('node-station');
  journey.hop = (journey.hop || 0) + 1;

  // ── gRPC side-call to go-grpc ──────────────────────────────────────────────
  await new Promise((resolve) => {
    const tracer = trace.getTracer('node-station');
    const span = tracer.startSpan('grpc.PassThrough');
    const ctx = trace.setSpan(context.active(), span);

    const metadata = new grpc.Metadata();
    // inject W3C trace context into gRPC metadata
    const carrier = {};
    propagation.inject(ctx, carrier);
    for (const [k, v] of Object.entries(carrier)) {
      metadata.set(k, v);
    }

    grpcClient.PassThrough(
      { journey_id: journey.journey_id, hop: journey.hop, stops: journey.stops },
      metadata,
      (err, response) => {
        span.end();
        if (!err && response) {
          journey.stops = response.stops;
        }
        resolve();
      }
    );
  });

  // ── Forward to next stop ───────────────────────────────────────────────────
  try {
    const carrier = {};
    propagation.inject(context.active(), carrier);
    await axios.post(nextStop, journey, { headers: { ...carrier, 'Content-Type': 'application/json' }, timeout: 30000 });
  } catch (e) {
    console.error('forward error:', e.message);
  }

  res.json({ status: 'passed', service: 'node-station', stops: journey.stops });
});

app.get('/health', (_, res) => res.json({ status: 'ok' }));

app.listen(3000, () => console.log('node-station on :3000'));
