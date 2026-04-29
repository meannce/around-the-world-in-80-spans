use axum::{
    extract::Json,
    http::HeaderMap,
    response::Json as RespJson,
    routing::{get, post},
    Router,
};
use opentelemetry::global;
use opentelemetry_otlp::WithExportConfig;
use opentelemetry_sdk::{propagation::TraceContextPropagator, runtime, Resource};
use opentelemetry_semantic_conventions::resource::SERVICE_NAME;
use serde::{Deserialize, Serialize};
use std::env;

#[derive(Debug, Serialize, Deserialize, Clone)]
struct Journey {
    journey_id: String,
    started_at: String,
    #[serde(default)]
    hop: u32,
    #[serde(default)]
    stops: Vec<String>,
}

fn init_tracer() {
    let endpoint = env::var("OTEL_EXPORTER_OTLP_ENDPOINT")
        .unwrap_or_else(|_| "http://otel-collector:4317".to_string());
    let svc_name = env::var("OTEL_SERVICE_NAME").unwrap_or_else(|_| "rust-station".to_string());

    global::set_text_map_propagator(TraceContextPropagator::new());

    let exporter = opentelemetry_otlp::new_exporter()
        .tonic()
        .with_endpoint(&endpoint)
        .build_span_exporter()
        .expect("otlp exporter");

    let tracer_provider = opentelemetry_sdk::trace::TracerProvider::builder()
        .with_batch_exporter(exporter, runtime::Tokio)
        .with_resource(Resource::new(vec![opentelemetry::KeyValue::new(
            SERVICE_NAME,
            svc_name,
        )]))
        .build();
    global::set_tracer_provider(tracer_provider);

    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::new("info"))
        .init();
}

async fn journey_handler(
    incoming: HeaderMap,
    Json(mut journey): Json<Journey>,
) -> RespJson<Journey> {
    journey.stops.push("rust-station".to_string());
    journey.hop += 1;

    let next_stop = env::var("NEXT_STOP")
        .unwrap_or_else(|_| "http://java-station:8082/journey".to_string());

    // Extract trace context from incoming headers and inject into outgoing
    let parent_cx = global::get_text_map_propagator(|prop| {
        prop.extract(&opentelemetry_http::HeaderExtractor(&incoming))
    });

    let mut out_headers = reqwest::header::HeaderMap::new();
    global::get_text_map_propagator(|prop| {
        prop.inject_context(
            &parent_cx,
            &mut opentelemetry_http::HeaderInjector(&mut out_headers),
        )
    });

    let client = reqwest::Client::new();
    let _ = client
        .post(&next_stop)
        .headers(out_headers)
        .json(&journey)
        .send()
        .await;

    RespJson(journey)
}

async fn health() -> &'static str {
    r#"{"status":"ok"}"#
}

#[tokio::main]
async fn main() {
    init_tracer();

    let app = Router::new()
        .route("/journey", post(journey_handler))
        .route("/health", get(health));

    let addr = "0.0.0.0:8001";
    println!("rust-station listening on {addr}");
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
