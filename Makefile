up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f

build:
	docker compose build

restart:
	docker compose restart

ps:
	docker compose ps

check:
	@echo "=== Core UI ===" && \
	curl -sf http://localhost        > /dev/null && echo "nginx        ✓" || echo "nginx        ✗" && \
	curl -sf http://localhost:5000   > /dev/null && echo "entry        ✓" || echo "entry        ✗" && \
	curl -sf http://localhost:16686  > /dev/null && echo "jaeger       ✓" || echo "jaeger       ✗" && \
	curl -sf http://localhost:3000   > /dev/null && echo "grafana      ✓" || echo "grafana      ✗" && \
	curl -sf http://localhost:9090   > /dev/null && echo "prometheus   ✓" || echo "prometheus   ✗"

press:
	curl -s -X POST http://localhost/press | python3 -m json.tool

journey-count:
	docker compose exec redis redis-cli get journey:total_count
