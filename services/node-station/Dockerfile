FROM node:22-alpine
WORKDIR /app
COPY package.json .
RUN npm install --omit=dev
COPY . .
# Copy the shared proto for gRPC client
COPY journey.proto .
CMD ["node", "index.js"]
