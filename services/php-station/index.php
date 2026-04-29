<?php
require __DIR__ . '/vendor/autoload.php';

use OpenTelemetry\API\Globals;
use OpenTelemetry\API\Trace\Propagation\TraceContextPropagator;
use OpenTelemetry\Contrib\Otlp\OtlpHttpTransportFactory;
use OpenTelemetry\Contrib\Otlp\SpanExporter;
use OpenTelemetry\SDK\Common\Attribute\Attributes;
use OpenTelemetry\SDK\Resource\ResourceInfo;
use OpenTelemetry\SDK\Sdk;
use OpenTelemetry\SDK\Trace\Sampler\AlwaysOnSampler;
use OpenTelemetry\SDK\Trace\SpanProcessor\BatchSpanProcessor;
use OpenTelemetry\SDK\Trace\TracerProvider;
use OpenTelemetry\SemConv\ResourceAttributes;
use GuzzleHttp\Client as GuzzleClient;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use Slim\Factory\AppFactory;

// ── Bootstrap OTel ───────────────────────────────────────────────────────────
$endpoint = getenv('OTEL_EXPORTER_OTLP_ENDPOINT') ?: 'http://otel-collector:4317';
$serviceName = getenv('OTEL_SERVICE_NAME') ?: 'php-station';

$transport = (new OtlpHttpTransportFactory())->create($endpoint . '/v1/traces', 'application/x-protobuf');
$exporter  = new SpanExporter($transport);

$tracerProvider = new TracerProvider(
    new BatchSpanProcessor($exporter),
    new AlwaysOnSampler(),
    ResourceInfo::create(Attributes::create([ResourceAttributes::SERVICE_NAME => $serviceName]))
);

Sdk::builder()
    ->setTracerProvider($tracerProvider)
    ->setPropagator(TraceContextPropagator::getInstance())
    ->setAutoShutdown(true)
    ->buildAndRegisterGlobal();

$tracer = Globals::tracerProvider()->getTracer('php-station');

// ── Slim app ─────────────────────────────────────────────────────────────────
$app = AppFactory::create();
$app->addBodyParsingMiddleware();

$app->post('/journey', function (Request $request, Response $response) use ($tracer): Response {
    $journey = $request->getParsedBody() ?? [];
    $journey['stops'][] = 'php-station';
    $journey['hop'] = ($journey['hop'] ?? 0) + 1;

    $nextStop = getenv('NEXT_STOP') ?: 'http://rust-station:8001/journey';

    // Extract parent context from incoming headers
    $carrier = [];
    foreach ($request->getHeaders() as $name => $values) {
        $carrier[strtolower($name)] = implode(',', $values);
    }
    $ctx = TraceContextPropagator::getInstance()->extract($carrier);

    $span = $tracer->spanBuilder('php-station.forward')
        ->setParent($ctx)
        ->startSpan();
    $scope = $span->activate();

    try {
        $outHeaders = ['Content-Type' => 'application/json'];
        TraceContextPropagator::getInstance()->inject($outHeaders);

        $client = new GuzzleClient(['timeout' => 30]);
        $client->post($nextStop, [
            'json'    => $journey,
            'headers' => $outHeaders,
        ]);
    } catch (\Throwable $e) {
        error_log("forward error: {$e->getMessage()}");
    } finally {
        $scope->detach();
        $span->end();
    }

    $response->getBody()->write(json_encode(['status' => 'passed', 'service' => 'php-station']));
    return $response->withHeader('Content-Type', 'application/json');
});

$app->get('/health', function (Request $request, Response $response): Response {
    $response->getBody()->write('{"status":"ok"}');
    return $response->withHeader('Content-Type', 'application/json');
});

$app->run();
