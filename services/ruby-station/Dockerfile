FROM ruby:3.3-alpine
RUN apk add --no-cache build-base
WORKDIR /app
COPY Gemfile .
RUN bundle install
COPY . .
CMD ["ruby", "app.rb"]
