# Catalog Management Service

A comprehensive musical works and recordings catalog management service for Downtown Music Publishing's unified Publishing Platform. Built with FastAPI, PostgreSQL, and designed for multi-tenant operation with industry-standard compliance (ISWC, ISRC, DDEX).

## 🎵 Features

### Core Capabilities
- **Musical Works Management**: ISWC-compliant work registration and management
- **Sound Recordings**: ISRC-compliant recording catalog with metadata
- **Songwriter Management**: Complete writer profiles with IPI/ISNI support
- **Multi-Tenant Architecture**: Row-Level Security (RLS) for complete data isolation
- **Advanced Search**: Full-text search with filters and faceted navigation
- **Event-Driven**: Real-time event publishing for catalog changes
- **Industry Standards**: ISWC, ISRC, ISO language codes, and PRO compliance

### Technical Features
- **FastAPI**: Modern, high-performance API with automatic OpenAPI documentation
- **PostgreSQL**: Robust database with Row-Level Security and full-text search
- **Multi-Tenant**: Complete tenant isolation with RLS policies
- **Authentication**: JWT-based authentication with role-based access
- **Rate Limiting**: Redis-based distributed rate limiting
- **Event Publishing**: SQS integration for event-driven architecture
- **Validation**: Comprehensive business rules and data validation
- **JSON:API**: Compliant API responses with relationships and sparse fieldsets

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Git

### 1. Clone and Setup
```bash
git clone <repository-url>
cd test-service

# Copy environment configuration
cp .env.example .env

# Review and update .env with your settings
vim .env
```

### 2. Start Services
```bash
# Run the automated setup script
./scripts/dev-setup.sh

# Or manually:
docker-compose up -d postgres redis
docker-compose --profile tools run --rm migrate
docker-compose up -d catalog-service
```

### 3. Verify Installation
```bash
# Check service health
curl http://localhost:8000/health

# Open API documentation
open http://localhost:8000/docs
```

## 📚 API Documentation

### Base URL
- **Local Development**: `http://localhost:8000`
- **API Version**: `v1`
- **API Prefix**: `/api/v1`

### Authentication
All API endpoints require JWT authentication via the `Authorization` header:
```bash
Authorization: Bearer <jwt-token>
```

### Tenant Context
Multi-tenant requests require the tenant ID header:
```bash
X-Tenant-ID: <tenant-uuid>
```

### Core Endpoints

#### Works Management
```bash
# List works
GET /api/v1/works?page=1&per_page=25

# Create work
POST /api/v1/works
{
  "data": {
    "type": "work",
    "attributes": {
      "title": "Yesterday",
      "genre": "Pop",
      "language": "en",
      "writers": [
        {
          "songwriter_id": "uuid",
          "role": "composer_lyricist",
          "contribution_percentage": 100.0
        }
      ]
    }
  }
}

# Get specific work
GET /api/v1/works/{work-id}

# Update work
PUT /api/v1/works/{work-id}

# Delete work
DELETE /api/v1/works/{work-id}
```

#### Songwriters Management
```bash
# List songwriters
GET /api/v1/songwriters

# Create songwriter
POST /api/v1/songwriters
{
  "data": {
    "type": "songwriter",
    "attributes": {
      "first_name": "John",
      "last_name": "Lennon",
      "stage_name": "John Lennon",
      "email": "john@example.com",
      "ipi": "123456789"
    }
  }
}
```

#### Search
```bash
# Global search
GET /api/v1/search?q=yesterday&types=work,songwriter

# Autocomplete
GET /api/v1/search/autocomplete?q=yester

# Similar resources
GET /api/v1/search/similar?resource_id=uuid&resource_type=work
```

### JSON:API Format
All responses follow JSON:API specification:
```json
{
  "data": {
    "type": "work",
    "id": "uuid",
    "attributes": {
      "title": "Yesterday",
      "genre": "Pop"
    },
    "relationships": {
      "writers": {
        "data": [
          {"type": "songwriter", "id": "uuid"}
        ]
      }
    }
  },
  "included": [
    {
      "type": "songwriter", 
      "id": "uuid",
      "attributes": {
        "first_name": "Paul",
        "last_name": "McCartney"
      }
    }
  ]
}
```

## 🏗️ Architecture

### Multi-Tenant Design
- **Row-Level Security (RLS)**: PostgreSQL policies ensure complete data isolation
- **Tenant Context**: Every request includes tenant ID for security
- **Audit Trails**: All changes tracked with tenant and user context

### Database Schema
- **Tenants**: Publisher organizations
- **Works**: Musical compositions with ISWC support
- **Songwriters**: Writer profiles with IPI/ISNI
- **Recordings**: Sound recordings with ISRC support
- **Work Writers**: Many-to-many relationships with roles and shares

### Event-Driven Architecture
- **Event Publishing**: Real-time events for all catalog changes
- **SQS Integration**: Reliable event delivery for downstream services
- **Event Types**: Create, update, delete events for all resources

### Security
- **JWT Authentication**: Industry-standard token-based auth
- **Role-Based Access**: Fine-grained permissions
- **Rate Limiting**: Protection against abuse
- **Input Validation**: Comprehensive data validation

## 🔧 Development

### Local Development Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Set up pre-commit hooks
pre-commit install

# Run database migrations
./scripts/run-migrations.sh

# Start development server
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Database Operations
```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Run migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1

# Show migration history
alembic history
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_works.py -v
```

### Code Quality
```bash
# Format code
black src/
isort src/

# Lint code
flake8 src/
mypy src/

# Run all quality checks
pre-commit run --all-files
```

## 🐳 Docker Deployment

### Build Image
```bash
docker build -t catalog-management-service .
```

### Production Deployment
```bash
# Use production compose file
docker-compose -f docker-compose.prod.yml up -d

# Or with environment-specific settings
ENV=production docker-compose up -d
```

### Environment Variables
Key environment variables for deployment:

```bash
# Database
DATABASE_URL=postgresql://user:password@host:5432/database
DATABASE_POOL_SIZE=20

# Security
JWT_SECRET_KEY=your-production-secret-key
DISABLE_AUTH=false

# Event Publishing
EVENT_BUS_TYPE=sqs
SQS_EVENT_QUEUE_URL=https://sqs.region.amazonaws.com/account/queue

# Monitoring
DATADOG_API_KEY=your-datadog-key
SENTRY_DSN=your-sentry-dsn

# Redis
REDIS_URL=redis://redis:6379/0

# Application
ENVIRONMENT=production
LOG_LEVEL=INFO
```

## 📊 Monitoring

### Health Checks
- **Service Health**: `GET /health`
- **Database Health**: `GET /health/database`
- **Dependencies**: `GET /health/dependencies`

### Metrics and Logging
- **Structured Logging**: JSON logs with request context
- **Request Tracing**: Unique request IDs for correlation
- **Performance Metrics**: Response times and throughput
- **Error Tracking**: Comprehensive error reporting

### Observability
- **OpenAPI Docs**: `http://localhost:8000/docs`
- **Health Dashboard**: `http://localhost:8000/health`
- **Request Logs**: Structured JSON with tenant/user context

## 🔒 Security

### Multi-Tenant Security
- **Row-Level Security**: PostgreSQL RLS policies
- **Tenant Validation**: Every request validates tenant access
- **Data Isolation**: Complete separation between tenants
- **Audit Logging**: All actions logged with tenant context

### Authentication & Authorization
- **JWT Tokens**: Secure, stateless authentication
- **Role-Based Access**: Granular permissions
- **Token Validation**: Comprehensive JWT validation
- **Session Management**: Secure token handling

### Data Protection
- **Input Validation**: Comprehensive request validation
- **SQL Injection Protection**: Parameterized queries
- **XSS Prevention**: Input sanitization
- **Rate Limiting**: Protection against abuse

## 🚧 Roadmap

### Phase 1 (Current)
- ✅ Core CRUD operations for works, songwriters, recordings
- ✅ Multi-tenant architecture with RLS
- ✅ JWT authentication and authorization
- ✅ Event publishing infrastructure
- ✅ Comprehensive validation and business rules

### Phase 2 (Planned)
- [ ] Advanced search with Elasticsearch integration
- [ ] Bulk operations for large-scale imports
- [ ] File upload and media management
- [ ] Advanced reporting and analytics
- [ ] GraphQL API support

### Phase 3 (Future)
- [ ] Real-time collaboration features
- [ ] Workflow management for registrations
- [ ] Integration with external PROs and DSPs
- [ ] Machine learning for duplicate detection
- [ ] Advanced rights management

## 🤝 Contributing

### Development Workflow
1. Fork the repository
2. Create a feature branch: `git checkout -b feature/new-feature`
3. Make your changes
4. Run tests: `pytest`
5. Check code quality: `pre-commit run --all-files`
6. Commit changes: `git commit -m "Add new feature"`
7. Push to branch: `git push origin feature/new-feature`
8. Create a Pull Request

### Code Standards
- **Python**: Follow PEP 8 style guide
- **Type Hints**: Use type annotations for all functions
- **Documentation**: Comprehensive docstrings for all modules
- **Testing**: Maintain 90%+ test coverage
- **Validation**: All inputs must be validated

### Pull Request Guidelines
- Include tests for new functionality
- Update documentation as needed
- Follow existing code patterns
- Add entry to CHANGELOG.md
- Ensure all CI checks pass

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

### Documentation
- **API Docs**: Available at `/docs` endpoint
- **OpenAPI Spec**: Available at `/openapi.json`
- **Health Checks**: Available at `/health`

### Getting Help
- **Issues**: Create GitHub issues for bugs and feature requests
- **Discussions**: Use GitHub Discussions for questions
- **Documentation**: Check the `/docs` endpoint for API documentation

### Contact
- **Team**: Downtown Music Publishing Development Team
- **Email**: tech@downtownmusic.com
- **Repository**: [GitHub Repository URL]

---

**Downtown Music Publishing** - Unified Publishing Platform