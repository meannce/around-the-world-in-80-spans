up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

check:
	curl -f http://localhost:3000 || echo "Grafana not ready"
	curl -f http://localhost:9090 || echo "Prometheus not ready"
