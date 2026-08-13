FROM node:22-slim
WORKDIR /app
RUN corepack enable
COPY frontend/ .
RUN pnpm install --frozen-lockfile && pnpm build && chown -R node /app
USER node
CMD ["pnpm", "start"]
