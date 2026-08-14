FROM node:20-alpine

WORKDIR /app

# Install dependencies
COPY frontend/package.json frontend/package-lock.json* ./frontend/
WORKDIR /app/frontend
RUN npm install

# Copy source code
COPY frontend/ ./

# Build the Next.js app
RUN npm run build

# Start the application
CMD ["npm", "start"]
