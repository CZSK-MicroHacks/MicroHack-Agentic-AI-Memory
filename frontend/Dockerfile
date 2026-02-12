FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency files
COPY package.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the application (skip tsc type-check, Vite handles transpilation)
RUN npx vite build

# Production stage - serve with a lightweight HTTP server
FROM nginx:alpine

# Copy built assets to nginx
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config template (envsubst resolves $BACKEND_URL at startup)
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Remove default config so the template takes precedence
RUN rm -f /etc/nginx/conf.d/default.conf

# Default backend URL (override via env var in ACA)
ENV BACKEND_URL=http://localhost:8000

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
