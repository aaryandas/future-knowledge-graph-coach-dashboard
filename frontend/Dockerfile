FROM node:22-slim
WORKDIR /app
RUN corepack enable
COPY frontend/ .
ARG BACKEND_URL
ENV BACKEND_URL=$BACKEND_URL
RUN pnpm install --frozen-lockfile && pnpm build && chown -R node /app
USER node
CMD ["pnpm", "start"]
