# around-the-world-in-80-spans

> A journey even Jules Verne wouldn't dare to write about.

One button press. One distributed trace. Every technology known to humanity.

## What is this?

Press the button → a single OpenTelemetry trace travels through **30+ technologies** before returning home. Every hop is a real child span. The whole journey is visible in Jaeger as one glorious waterfall.

## The Journey

```
Browser
  → Nginx (reverse proxy)
    → Python/Flask (entry)
      ├── Redis           (cache)
      ├── PostgreSQL      (relational SQL)
      ├── MySQL           (relational SQL)
      ├── MongoDB         (document store)
      ├── Memcached       (in-memory cache)
      ├── Elasticsearch   (search engine)
      ├── InfluxDB        (time-series)
      ├── MinIO           (object storage)
      ├── Neo4j           (graph database)
      ├── ClickHouse      (analytical DB)
      ├── ScyllaDB        (wide-column / Cassandra)
      ├── CockroachDB     (distributed SQL)
      └── Meilisearch     (search engine)
        → Kafka (async message bus)
          → Go (Kafka consumer)
            → Node.js/Express
              ├── Go gRPC service (side call via gRPC)
              └── → Ruby/Sinatra
                    → PHP/Slim
                      → Rust/Axum
                        → Java/Spring Boot
                          → C#/.NET ASP.NET Core
                            → Elixir/Plug
                              → RabbitMQ (AMQP)
                                → Python (RabbitMQ consumer)
                                  → NATS (pub/sub)
                                    → Node.js (NATS consumer)
                                      → MQTT (Mosquitto)
                                        → Python (MQTT consumer)
                                          → Python/Flask /finalize ✓
```

**Languages:** Python, Go, Node.js, Ruby, PHP, Rust, Java, C#, Elixir

**Protocols:** HTTP/1.1, gRPC, Kafka, AMQP, NATS, MQTT

**Databases:** Redis, PostgreSQL, MySQL, MongoDB, Memcached, Elasticsearch, InfluxDB, MinIO, Neo4j, ClickHouse, ScyllaDB, CockroachDB, Meilisearch

**Messaging:** Kafka, RabbitMQ, NATS, MQTT

**Observability:** OTel Collector, Jaeger, Prometheus, Grafana, Loki

## Quick Start

```bash
make up
```

Then open http://localhost and press the button.

Watch the trace at http://localhost:16686 (Jaeger).

## Ports

| Service       | Port  | URL                        |
|---------------|-------|----------------------------|
| App (nginx)   | 80    | http://localhost           |
| Jaeger UI     | 16686 | http://localhost:16686     |
| Grafana       | 3000  | http://localhost:3000      |
| Prometheus    | 9090  | http://localhost:9090      |
| InfluxDB      | 8086  | http://localhost:8086      |
| MinIO console | 9001  | http://localhost:9001      |
| Neo4j browser | 7474  | http://localhost:7474      |
| ClickHouse    | 8123  | http://localhost:8123      |
| CockroachDB   | 8080  | http://localhost:8080      |
| RabbitMQ mgmt | 15672 | http://localhost:15672     |

## Commands

```bash
make up       # build + start everything
make down     # stop and remove volumes
make logs     # follow all logs
make check    # health check core services
make press    # send a journey from the CLI
```

## Resource requirements

This is ~38 containers. Recommended: **16GB RAM**, 4+ CPU cores. It will run on 8GB but slowly.

To disable heavy services (Neo4j, ScyllaDB, ClickHouse), comment them out of `compose.yaml`.
