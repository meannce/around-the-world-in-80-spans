import os, uuid, json, time, logging, io
from datetime import datetime, timezone
from flask import Flask, request, jsonify, Response

# ── OpenTelemetry bootstrap ──────────────────────────────────────────────────
from opentelemetry import trace
from opentelemetry.propagate import inject, extract
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.pymysql import PyMySQLInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

resource = Resource.create({SERVICE_NAME: os.environ.get("OTEL_SERVICE_NAME", "entry")})
provider = TracerProvider(resource=resource)
otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
trace.set_tracer_provider(provider)

FlaskInstrumentor().instrument()
RedisInstrumentor().instrument()
Psycopg2Instrumentor().instrument()
PyMySQLInstrumentor().instrument()
PymongoInstrumentor().instrument()
RequestsInstrumentor().instrument()

tracer = trace.get_tracer("entry")
log = logging.getLogger("entry")
logging.basicConfig(level=logging.INFO)

# ── Lazy clients (retry-safe) ────────────────────────────────────────────────
import redis as _redis
import psycopg2, pymysql, pymongo
import pymemcache.client.base as _mc
from elasticsearch import Elasticsearch
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from minio import Minio
from kafka import KafkaProducer
from neo4j import GraphDatabase
import clickhouse_connect
import requests

_redis_client = None
_es_client     = None
_influx_write  = None
_minio_client  = None
_kafka_producer = None
_neo4j_driver  = None
_ch_client     = None
_mc_client     = None

def redis_client():
    global _redis_client
    if _redis_client is None:
        _redis_client = _redis.from_url(os.environ["REDIS_URL"])
    return _redis_client

def es_client():
    global _es_client
    if _es_client is None:
        _es_client = Elasticsearch(os.environ["ELASTICSEARCH_URL"])
    return _es_client

def influx_write_api():
    global _influx_write
    if _influx_write is None:
        c = InfluxDBClient(
            url=os.environ["INFLUXDB_URL"],
            token=os.environ["INFLUXDB_TOKEN"],
            org=os.environ["INFLUXDB_ORG"],
        )
        _influx_write = c.write_api(write_options=SYNCHRONOUS)
    return _influx_write

def minio_client():
    global _minio_client
    if _minio_client is None:
        _minio_client = Minio(
            os.environ["MINIO_ENDPOINT"],
            access_key=os.environ["MINIO_ACCESS_KEY"],
            secret_key=os.environ["MINIO_SECRET_KEY"],
            secure=False,
        )
        if not _minio_client.bucket_exists("journeys"):
            _minio_client.make_bucket("journeys")
    return _minio_client

def kafka_producer():
    global _kafka_producer
    if _kafka_producer is None:
        _kafka_producer = KafkaProducer(
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            value_serializer=lambda v: json.dumps(v).encode(),
        )
    return _kafka_producer

def neo4j_driver():
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=None)
    return _neo4j_driver

def ch_client():
    global _ch_client
    if _ch_client is None:
        _ch_client = clickhouse_connect.get_client(
            host="clickhouse", port=8123, database="default"
        )
        _ch_client.command(
            "CREATE TABLE IF NOT EXISTS journeys "
            "(journey_id String, ts DateTime DEFAULT now()) "
            "ENGINE = MergeTree() ORDER BY ts"
        )
    return _ch_client

def mc_client():
    global _mc_client
    if _mc_client is None:
        host, port = os.environ.get("MEMCACHED_HOST", "memcached:11211").split(":")
        _mc_client = _mc.Client((host, int(port)))
    return _mc_client

# ── Journey tracking ─────────────────────────────────────────────────────────
journeys: dict[str, dict] = {}

# ── Flask app ────────────────────────────────────────────────────────────────
app = Flask(__name__)

@app.route("/")
def home():
    return Response(HOME_HTML, mimetype="text/html")

@app.route("/press", methods=["POST"])
def press():
    journey_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    journeys[journey_id] = {"status": "travelling", "stops": [], "started_at": started_at}

    ctx = trace.get_current_span().get_span_context()
    trace_id_hex = format(ctx.trace_id, "032x") if ctx.is_valid else "?"

    with tracer.start_as_current_span("journey.start") as span:
        span.set_attribute("journey.id", journey_id)
        span.set_attribute("journey.trace_id", trace_id_hex)

        payload = {"journey_id": journey_id, "started_at": started_at, "hop": 0, "stops": []}

        # ── STOP 1: Redis ───────────────────────────────────────────────────
        with tracer.start_as_current_span("stop.redis"):
            try:
                r = redis_client()
                r.set(f"journey:{journey_id}", "started")
                r.incr("journey:total_count")
                journeys[journey_id]["stops"].append("redis")
            except Exception as e:
                log.warning(f"Redis: {e}")

        # ── STOP 2: PostgreSQL ──────────────────────────────────────────────
        with tracer.start_as_current_span("stop.postgresql"):
            try:
                conn = psycopg2.connect(os.environ["POSTGRES_DSN"])
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "CREATE TABLE IF NOT EXISTS journeys "
                            "(id TEXT PRIMARY KEY, started_at TIMESTAMPTZ)"
                        )
                        cur.execute(
                            "INSERT INTO journeys VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (journey_id, started_at)
                        )
                conn.close()
                journeys[journey_id]["stops"].append("postgresql")
            except Exception as e:
                log.warning(f"PostgreSQL: {e}")

        # ── STOP 3: MySQL ───────────────────────────────────────────────────
        with tracer.start_as_current_span("stop.mysql"):
            try:
                conn = pymysql.connect(
                    host=os.environ["MYSQL_HOST"],
                    user=os.environ["MYSQL_USER"],
                    password=os.environ["MYSQL_PASSWORD"],
                    database=os.environ["MYSQL_DB"],
                )
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "CREATE TABLE IF NOT EXISTS journeys "
                            "(id VARCHAR(36) PRIMARY KEY, started_at DATETIME)"
                        )
                        cur.execute(
                            "INSERT IGNORE INTO journeys VALUES (%s, %s)",
                            (journey_id, started_at)
                        )
                    conn.commit()
                journeys[journey_id]["stops"].append("mysql")
            except Exception as e:
                log.warning(f"MySQL: {e}")

        # ── STOP 4: MongoDB ─────────────────────────────────────────────────
        with tracer.start_as_current_span("stop.mongodb"):
            try:
                client = pymongo.MongoClient(os.environ["MONGO_URI"])
                db = client["journey"]
                db["journeys"].insert_one({"_id": journey_id, "started_at": started_at})
                client.close()
                journeys[journey_id]["stops"].append("mongodb")
            except Exception as e:
                log.warning(f"MongoDB: {e}")

        # ── STOP 5: Memcached ───────────────────────────────────────────────
        with tracer.start_as_current_span("stop.memcached"):
            try:
                mc_client().set(f"journey:{journey_id}", b"started", expire=3600)
                journeys[journey_id]["stops"].append("memcached")
            except Exception as e:
                log.warning(f"Memcached: {e}")

        # ── STOP 6: Elasticsearch ───────────────────────────────────────────
        with tracer.start_as_current_span("stop.elasticsearch"):
            try:
                es_client().index(
                    index="journeys",
                    id=journey_id,
                    document={"journey_id": journey_id, "started_at": started_at, "status": "started"},
                )
                journeys[journey_id]["stops"].append("elasticsearch")
            except Exception as e:
                log.warning(f"Elasticsearch: {e}")

        # ── STOP 7: InfluxDB ────────────────────────────────────────────────
        with tracer.start_as_current_span("stop.influxdb"):
            try:
                p = Point("journey_start").tag("journey_id", journey_id).field("hop", 0)
                influx_write_api().write(
                    bucket=os.environ["INFLUXDB_BUCKET"],
                    org=os.environ["INFLUXDB_ORG"],
                    record=p,
                )
                journeys[journey_id]["stops"].append("influxdb")
            except Exception as e:
                log.warning(f"InfluxDB: {e}")

        # ── STOP 8: MinIO ───────────────────────────────────────────────────
        with tracer.start_as_current_span("stop.minio"):
            try:
                data = json.dumps(payload).encode()
                minio_client().put_object(
                    "journeys",
                    f"{journey_id}/manifest.json",
                    io.BytesIO(data),
                    len(data),
                    content_type="application/json",
                )
                journeys[journey_id]["stops"].append("minio")
            except Exception as e:
                log.warning(f"MinIO: {e}")

        # ── STOP 9: Neo4j ───────────────────────────────────────────────────
        with tracer.start_as_current_span("stop.neo4j"):
            try:
                with neo4j_driver().session() as session:
                    session.run(
                        "MERGE (j:Journey {id: $id}) SET j.started_at = $ts",
                        id=journey_id, ts=started_at
                    )
                journeys[journey_id]["stops"].append("neo4j")
            except Exception as e:
                log.warning(f"Neo4j: {e}")

        # ── STOP 10: ClickHouse ─────────────────────────────────────────────
        with tracer.start_as_current_span("stop.clickhouse"):
            try:
                ch_client().command(
                    f"INSERT INTO journeys (journey_id) VALUES ('{journey_id}')"
                )
                journeys[journey_id]["stops"].append("clickhouse")
            except Exception as e:
                log.warning(f"ClickHouse: {e}")

        # ── STOP 11: ScyllaDB (Cassandra-compatible) ────────────────────────
        with tracer.start_as_current_span("stop.scylladb"):
            try:
                from cassandra.cluster import Cluster
                cluster = Cluster([os.environ.get("SCYLLA_HOST", "scylladb")])
                session = cluster.connect()
                session.execute(
                    "CREATE KEYSPACE IF NOT EXISTS journey "
                    "WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}"
                )
                session.execute(
                    "CREATE TABLE IF NOT EXISTS journey.journeys "
                    "(id text PRIMARY KEY, started_at text)"
                )
                session.execute(
                    "INSERT INTO journey.journeys (id, started_at) VALUES (%s, %s)",
                    (journey_id, started_at)
                )
                cluster.shutdown()
                journeys[journey_id]["stops"].append("scylladb")
            except Exception as e:
                log.warning(f"ScyllaDB: {e}")

        # ── STOP 12: CockroachDB ────────────────────────────────────────────
        with tracer.start_as_current_span("stop.cockroachdb"):
            try:
                conn = psycopg2.connect(os.environ.get("COCKROACH_DSN", ""))
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "CREATE TABLE IF NOT EXISTS journeys "
                            "(id TEXT PRIMARY KEY, started_at TEXT)"
                        )
                        cur.execute(
                            "INSERT INTO journeys VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (journey_id, started_at)
                        )
                conn.close()
                journeys[journey_id]["stops"].append("cockroachdb")
            except Exception as e:
                log.warning(f"CockroachDB: {e}")

        # ── STOP 13: Meilisearch ────────────────────────────────────────────
        with tracer.start_as_current_span("stop.meilisearch"):
            try:
                requests.post(
                    f"{os.environ.get('MEILISEARCH_URL', 'http://meilisearch:7700')}/indexes/journeys/documents",
                    json=[{"id": journey_id, "started_at": started_at}],
                    headers={
                        "Authorization": f"Bearer {os.environ.get('MEILISEARCH_KEY', '')}",
                        "Content-Type": "application/json",
                    },
                    timeout=5,
                )
                journeys[journey_id]["stops"].append("meilisearch")
            except Exception as e:
                log.warning(f"Meilisearch: {e}")

        # ── STOP 14: Kafka (async relay to the rest of the world) ───────────
        with tracer.start_as_current_span("stop.kafka.publish") as span:
            try:
                headers = {}
                inject(headers)  # inject W3C traceparent into dict
                kafka_headers = [(k, v.encode()) for k, v in headers.items()]

                payload["stops"] = journeys[journey_id]["stops"]
                kafka_producer().send(
                    "journey",
                    value=payload,
                    headers=kafka_headers,
                )
                kafka_producer().flush()
                journeys[journey_id]["stops"].append("kafka")
                span.set_attribute("messaging.system", "kafka")
                span.set_attribute("messaging.destination", "journey")
            except Exception as e:
                log.warning(f"Kafka: {e}")

    return jsonify({
        "journey_id": journey_id,
        "trace_id": trace_id_hex,
        "jaeger_url": f"http://localhost:16686/trace/{trace_id_hex}",
        "status": "travelling",
        "stops_so_far": journeys[journey_id]["stops"],
    })


@app.route("/finalize", methods=["POST"])
def finalize():
    """Called by mqtt-consumer at the very end of the journey."""
    data = request.json or {}
    journey_id = data.get("journey_id", "unknown")
    final_stops = data.get("stops", [])

    if journey_id in journeys:
        journeys[journey_id]["status"] = "complete"
        journeys[journey_id]["stops"] = final_stops
        journeys[journey_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

    with tracer.start_as_current_span("journey.complete") as span:
        span.set_attribute("journey.id", journey_id)
        span.set_attribute("journey.total_stops", len(final_stops))
        log.info(f"Journey {journey_id} complete! {len(final_stops)} stops.")

    return jsonify({"status": "complete", "journey_id": journey_id})


@app.route("/status/<journey_id>")
def status(journey_id):
    return jsonify(journeys.get(journey_id, {"status": "not_found"}))


@app.route("/metrics")
def metrics():
    total = len(journeys)
    complete = sum(1 for j in journeys.values() if j.get("status") == "complete")
    return f"journeys_total {total}\njourneys_complete {complete}\n"


HOME_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Around the World in 80 Spans</title>
  <style>
    body { background: #0a0a0a; color: #00ff88; font-family: monospace; text-align: center; padding: 40px; }
    h1 { font-size: 2.5em; text-shadow: 0 0 20px #00ff88; }
    .subtitle { color: #888; margin-bottom: 40px; }
    button {
      font-size: 2em; background: #0a0a0a; color: #00ff88;
      border: 2px solid #00ff88; padding: 20px 50px; cursor: pointer;
      text-shadow: 0 0 10px #00ff88; box-shadow: 0 0 20px #00ff4433;
      transition: all 0.2s;
    }
    button:hover { background: #00ff8822; box-shadow: 0 0 40px #00ff8866; }
    #result { margin-top: 40px; }
    .journey-card {
      border: 1px solid #00ff8844; padding: 20px; margin: 20px auto;
      max-width: 700px; text-align: left; background: #0f1a0f;
    }
    .stop { color: #00aaff; }
    a { color: #ff8800; }
    .tech-list { color: #666; font-size: 0.8em; max-width: 800px; margin: 0 auto 40px; }
  </style>
</head>
<body>
  <h1>🌍 Around the World in 80 Spans</h1>
  <p class="subtitle">One button press. One trace. Every technology known to humanity.</p>
  <p class="tech-list">
    nginx → python → redis → postgresql → mysql → mongodb → memcached → elasticsearch →
    influxdb → minio → neo4j → clickhouse → scylladb → cockroachdb → meilisearch →
    kafka → go → node.js → grpc → ruby → php → rust → java → .net → elixir →
    rabbitmq → python → nats → node.js → mqtt → python → home
  </p>
  <button onclick="startJourney()">SEND THE SPAN</button>
  <div id="result"></div>

  <script>
    async function startJourney() {
      document.getElementById('result').innerHTML = '<p>🚀 Journey started...</p>';
      const r = await fetch('/press', { method: 'POST' });
      const data = await r.json();
      document.getElementById('result').innerHTML = `
        <div class="journey-card">
          <p>🆔 Journey ID: <b>${data.journey_id}</b></p>
          <p>🔍 Trace ID: <b>${data.trace_id}</b></p>
          <p>📊 <a href="${data.jaeger_url}" target="_blank">Open in Jaeger →</a></p>
          <p>🏁 Stops so far: <span class="stop">${data.stops_so_far.join(' → ')}</span></p>
          <p><small>The span is still travelling through ${30 - data.stops_so_far.length}+ more technologies...</small></p>
        </div>
      `;
      setTimeout(() => pollStatus(data.journey_id), 3000);
    }

    async function pollStatus(id) {
      const r = await fetch('/status/' + id);
      const data = await r.json();
      const card = document.querySelector('.journey-card');
      if (card) {
        card.querySelector('.stop').textContent = (data.stops || []).join(' → ');
        if (data.status === 'complete') {
          card.innerHTML += '<p style="color:#ff8800;">✅ Journey complete! ' + (data.stops||[]).length + ' stops total.</p>';
        } else {
          setTimeout(() => pollStatus(id), 2000);
        }
      }
    }
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
