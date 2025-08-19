# syntax=docker/dockerfile:1

ARG NODE_VERSION=20.16.0

################################################################################
# Use node image for base image for all stages.
FROM node:${NODE_VERSION}-alpine as base

WORKDIR /usr/src/app

################################################################################
# Install production dependencies
FROM base as deps

RUN --mount=type=bind,source=package.json,target=package.json \
    --mount=type=bind,source=package-lock.json,target=package-lock.json \
    --mount=type=cache,target=/root/.npm \
    npm ci --omit=dev

################################################################################
# Build stage with devDependencies (to build app)
FROM deps as build

RUN --mount=type=bind,source=package.json,target=package.json \
    --mount=type=bind,source=package-lock.json,target=package-lock.json \
    --mount=type=cache,target=/root/.npm \
    npm ci

COPY . .

RUN npm run build

################################################################################
# Final stage: minimal image serving built files with static server
FROM base as final

ENV NODE_ENV production

# Copy package files
COPY package.json package-lock.json ./

# Install serve package to serve static files
RUN npm install serve

# Copy production node_modules (except serve will be added above)
COPY --from=deps /usr/src/app/node_modules ./node_modules

# Copy build output
COPY --from=build /usr/src/app/dist ./dist

# Use node user
USER node

# Expose port 5173
EXPOSE 5173

# Run 'serve' to serve static files from dist folder
CMD ["npx", "serve", "-s", "dist", "-l", "5173"]
