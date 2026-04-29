FROM php:8.3-cli-alpine
RUN apk add --no-cache curl git && \
    curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer
WORKDIR /app
COPY composer.json .
RUN composer install --no-dev --optimize-autoloader --ignore-platform-req=ext-opentelemetry
COPY . .
EXPOSE 8000
CMD ["php", "-S", "0.0.0.0:8000", "index.php"]
