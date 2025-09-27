# Casey's Panel Backend

HIPAA-compliant medical workflow management system with AI agents.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start development server
python -m uvicorn app.main:app --reload

# Start production server
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app
```

## Environment Variables

```bash
DATABASE_URL=postgresql://user:pass@localhost/caseys_panel
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
JWT_SECRET_KEY=your_jwt_secret_256_bits_minimum
```

## API Endpoints

- Health: `/healthz`
- Documentation: `/docs`
- Workflows: `/api/v1/workflows`
- Authentication: `/api/v1/auth`

## Deployment

Automatically deploys to Azure App Service via GitHub Actions on push to main branch.