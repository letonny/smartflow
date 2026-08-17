Real-time traffic analytics platform that ingests traffic, weather, construction, and accident data to identify congestion, predict travel times, and visualize transportation trends

This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## SmartFlow Workspace Setup

SmartFlow is a real-time traffic intelligence and predictive analytics platform composed of:
1. **Next.js Frontend (React + TypeScript):** Standard modern web application.
2. **FastAPI Backend (Python + asyncpg):** High-performance asynchronous API endpoints connecting to PostGIS.
3. **ETL Pipeline:** Scheduled data ingestion and validation for traffic, weather, incidents, and construction.

### Local Installation

1. **Next.js Frontend:**
   ```bash
   npm install
   ```
2. **Python Virtual Environment & Requirements:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   pip install fastapi
   ```

### Environment Configuration
Copy the provided `.env.example` template into a new `.env` file and customize your configuration (especially the `DATABASE_URL` with PostGIS support):
```bash
cp .env.example .env
```

### Database Seeding
Ensure your local PostgreSQL/PostGIS server is active, then seed the database with high-fidelity, realistic San Francisco Bay Area geographical road segments, active incidents, weather station snapshots, and traffic logs:
```bash
.venv/bin/python3 app/database/seed.py
```

### Running the Applications

1. **Start the Next.js Frontend:**
   ```bash
   npm run dev
   ```
2. **Start the FastAPI Backend:**
   ```bash
   .venv/bin/python3 -m uvicorn app.backend.main:app --reload --port 8000
   ```
3. **Start the ETL Scheduler:**
   ```bash
   .venv/bin/python3 app/etl/scheduler.py
   ```

### Running Tests
To verify code correctness and ensure integrity across both the API and the pipeline:
```bash
# Run backend tests
.venv/bin/python3 -m unittest app/backend/test_backend.py

# Run ETL tests
.venv/bin/python3 -m unittest app/etl/test_pipeline.py
```

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
