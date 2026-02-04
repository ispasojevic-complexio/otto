# Otto Implementation Plan - Complete Specification

## Project Overview
Otto is a car sales analytics platform that crawls polovniautomobili.com, processes car ad data through an event-driven pipeline, and provides real-time insights via an AI chatbot.

## Final Architecture Components

### Component Names (Updated)
```
otto/
├── components/
│   ├── crawler_scheduler/     # Manages crawl queue and priorities
│   ├── page_fetcher/          # Downloads and caches web pages
│   ├── url_extractor/         # Finds URLs in downloaded pages
│   ├── ad_parser/             # Extracts structured car ad data
│   ├── url_filter/            # Deduplication with bloom filter
│   ├── ad_monitor/            # Tracks ad lifecycle and removals
│   ├── stream_processor/      # Apache Flink analytics engine
│   ├── query_service_mcp/     # MCP server for data queries
│   └── chat_api/              # Chatbot backend API
├── shared/
│   ├── models/                # Pydantic data models
│   ├── kafka/                 # Kafka utilities
│   └── redis/                 # Redis utilities
├── tests/
│   ├── fixtures/              # Test containers and mocks
│   └── samples/               # Sample HTML files
└── scripts/                   # Deployment and utility scripts
```

## Architecture Decisions

### Communication Patterns
- **Redis Queues**: Fast, direct component communication
  - URL Extractor → URL Filter
  - Crawler Scheduler ↔ Page Fetcher
- **Kafka Topics**: Major events and audit trail
  - `webpage_log`: Page download events
  - `ad_added_log`: New car ads discovered
  - `ad_removed_log`: Ads marked as removed

### Data Retention Policies
- **Kafka logs**: 1 year retention (configurable)
- **Redis webpage cache**: 1 hour TTL (configurable)
- **PostgreSQL**: Permanent storage for aggregated analytics
- **No archival** to external storage initially

### Deployment Model
- **Single instance** per component initially
- **Docker containers** for each service
- **Kafka consumers** designed for horizontal scaling (future)
- **Checkpoint/state management** per component

## Infrastructure Setup

### Docker Compose Services
```yaml
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes: ["redis_data:/data"]

  kafka:
    image: confluentinc/cp-kafka:latest
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_LOG_RETENTION_MS: 31536000000  # 1 year

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: otto_analytics
      POSTGRES_USER: otto
      POSTGRES_PASSWORD: otto_pass
    volumes: ["postgres_data:/var/lib/postgresql/data"]

  prometheus:
    image: prom/prometheus:latest
    volumes: ["./prometheus.yml:/etc/prometheus/prometheus.yml"]

  grafana:
    image: grafana/grafana:latest
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
```

### Environment Configuration
```env
# Redis
REDIS_URL=redis://localhost:6379
REDIS_CACHE_TTL=3600

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_RETENTION_MS=31536000000

# PostgreSQL
POSTGRES_DSN=postgresql://otto:otto_pass@localhost/otto_analytics

# Crawling Configuration
CRAWLER_RATE_LIMIT=1
CRAWLER_RETRY_COUNT=3
CRAWLER_BACKOFF_BASE=2
CRAWLER_POLITENESS_DELAY=1

# URL Filter
BLOOM_FILTER_SIZE=1000000
BLOOM_FILTER_ERROR_RATE=0.0001
BLOOM_FILTER_PERSIST_INTERVAL=1000

# Ad Monitor
AD_MONITOR_CHECK_INTERVAL=86400  # Daily
AD_MONITOR_BATCH_SIZE=1000

# Initial Setup
SEED_URL_COUNT=50
CRAWL_DOMAIN=polovniautomobili.com
```

## Component Specifications

### 1. Crawler Scheduler
**Purpose**: Manages URL crawling queue with priorities

**Inputs**:
- Seed URLs (configuration file)
- New URLs from URL Filter (Redis queue: `url_filter_output`)

**Outputs**:
- URLs to crawl (Redis queue: `crawler_queue`)

**Key Features**:
- Priority-based queuing (3 levels: high, medium, low)
- Deduplication check via Bloom filter
- Rate limiting coordination
- Checkpoint mechanism for queue state

**Configuration**:
- `MAX_QUEUE_SIZE=100000`
- `PRIORITY_LEVELS=3`
- `CHECKPOINT_INTERVAL=1000`

### 2. Page Fetcher
**Purpose**: Downloads web pages with caching and retry logic

**Inputs**:
- URLs to fetch (Redis queue: `crawler_queue`)

**Outputs**:
- Downloaded pages (Redis cache + Kafka: `webpage_log`)

**Key Features**:
- httpx async client with connection pooling
- Exponential backoff retry (3 attempts max)
- Redis caching with configurable TTL
- Dead Letter Queue for permanent failures
- Rate limiting (1 req/sec to target domain)

**Caching Strategy**:
- Key pattern: `webpage:{sha256(url)}`
- TTL: 1 hour (configurable)
- Content compression for large pages

### 3. URL Extractor
**Purpose**: Extracts URLs from downloaded pages

**Inputs**:
- Page content (Kafka consumer: `webpage_log`)

**Outputs**:
- Extracted URLs (Redis queue: `url_extractor_output`)

**Key Features**:
- BeautifulSoup4 HTML parsing
- URL pattern matching for car ads and search pages
- Domain filtering (pouze polovniautomobili.com)
- URL normalization and validation

### 4. Ad Parser
**Purpose**: Extracts structured car data from HTML pages

**Inputs**:
- Page content for car ads (Kafka consumer: `webpage_log`)

**Outputs**:
- Structured car data (Kafka: `ad_added_log`)

**Data Model**:
```python
class CarAd(BaseModel):
    url: str
    ad_id: str
    make: str
    model: str
    year: int
    price: float
    currency: str = "EUR"
    mileage: Optional[int] = None
    fuel_type: Optional[str] = None
    transmission: Optional[str] = None  # "manual" | "automatic"
    city: Optional[str] = None
    country_origin: Optional[str] = None
    first_registration: Optional[str] = None
    engine_volume: Optional[float] = None
    power_kw: Optional[int] = None
    extracted_at: datetime
    parser_version: str = "v1.0"
```

**Parser Versioning**:
- Multiple parser strategies per version
- Fallback mechanism for structure changes
- Parser performance metrics

### 5. URL Filter
**Purpose**: Filters duplicate and irrelevant URLs

**Inputs**:
- URLs from URL Extractor (Redis queue: `url_extractor_output`)

**Outputs**:
- Filtered URLs (Redis queue: `url_filter_output`)

**Key Features**:
- Redis-backed Bloom filter for seen URLs
- Domain whitelist filtering
- URL normalization before filtering
- Periodic filter persistence and cleanup

**Bloom Filter Configuration**:
- Expected items: 1,000,000
- False positive rate: 0.01%
- Persistence interval: every 1000 URLs

### 6. Ad Monitor
**Purpose**: Tracks ad lifecycle and detects removals

**Scheduling**: Daily cron job at 2 AM

**Process**:
1. Query all active ads from previous crawls
2. Check ad availability with HEAD requests
3. Detect removed/archived ads
4. Publish removal events

**Outputs**:
- Ad removal events (Kafka: `ad_removed_log`)

**Detection Logic**:
```python
status_mapping = {
    404: "removed",
    301: "moved_or_sold",
    302: "moved_or_sold",
    403: "access_denied",
    200: "active"
}
```

### 7. Stream Processor (Apache Flink)
**Purpose**: Real-time analytics and aggregations

**Inputs**:
- Car ad events (Kafka: `ad_added_log`, `ad_removed_log`)

**Outputs**:
- Aggregated metrics (PostgreSQL tables)

**Aggregation Windows**:
- Tumbling window: 24 hours OR 100k records (whichever comes first)
- Session windows for user behavior (future)

**Initial Metrics**:
```python
metrics = [
    "avg_price_by_make_model",
    "total_ads_by_city",
    "price_distribution_by_year",
    "ads_added_removed_daily",
    "popular_makes_models",
    "average_time_on_market",
    "depreciation_trends"
]
```

### 8. Query Service MCP
**Purpose**: MCP server providing analytics query capabilities

**MCP Tools**:
```python
tools = [
    "get_average_price(make, model, year_range, city)",
    "get_trending_cars(time_period, metric)",
    "get_depreciation_rate(make, model, years)",
    "find_good_deals(criteria)",
    "get_market_insights(region, time_period)",
    "compare_prices(make1_model1, make2_model2)",
    "get_inventory_levels(make, model, region)"
]
```

**Database Connection**:
- asyncpg connection pool (min: 5, max: 20)
- Query timeout: 30 seconds
- Response caching for expensive queries

### 9. Chat API
**Purpose**: Backend API for chatbot interactions

**Framework**: FastAPI with async support

**Endpoints**:
```python
POST /chat
    - Input: {"message": str, "session_id": str}
    - Output: {"response": str, "query_info": dict}

GET /health
    - Health check for all dependencies

WebSocket /ws/{session_id}
    - Real-time chat interface
```

**LLM Integration**:
- Claude API via MCP protocol
- Query understanding and SQL generation
- Natural language response formatting

## Database Schema

### PostgreSQL Tables
```sql
-- Aggregated car metrics
CREATE TABLE car_metrics (
    id SERIAL PRIMARY KEY,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    make VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    avg_price DECIMAL(12,2),
    min_price DECIMAL(12,2),
    max_price DECIMAL(12,2),
    median_price DECIMAL(12,2),
    total_ads INTEGER,
    avg_mileage INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Ad lifecycle tracking
CREATE TABLE ad_lifecycle (
    ad_id VARCHAR(100) PRIMARY KEY,
    url TEXT NOT NULL,
    make VARCHAR(100),
    model VARCHAR(100),
    year INTEGER,
    initial_price DECIMAL(12,2),
    first_seen TIMESTAMP NOT NULL,
    last_seen TIMESTAMP,
    removal_detected TIMESTAMP,
    days_active INTEGER,
    status VARCHAR(20) DEFAULT 'active'
);

-- Daily market summary
CREATE TABLE daily_market_summary (
    date DATE PRIMARY KEY,
    total_ads_added INTEGER,
    total_ads_removed INTEGER,
    avg_price DECIMAL(12,2),
    most_popular_make VARCHAR(100),
    most_popular_model VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Performance indexes
CREATE INDEX idx_car_metrics_make_model ON car_metrics(make, model);
CREATE INDEX idx_car_metrics_window ON car_metrics(window_start, window_end);
CREATE INDEX idx_ad_lifecycle_status ON ad_lifecycle(status);
CREATE INDEX idx_ad_lifecycle_dates ON ad_lifecycle(first_seen, removal_detected);
```

## Development Workflow

### Project Setup
```bash
# Initialize project
cd otto
uv init
uv add pydantic httpx redis aiokafka asyncpg fastapi

# Development dependencies
uv add --dev pytest pytest-asyncio testcontainers pyright ruff

# Pre-commit setup
uv add --dev pre-commit
pre-commit install
```

### Testing Strategy

**Unit Tests** (80% coverage target):
```python
# Test fixtures with testcontainers
@pytest.fixture
async def redis_container():
    with testcontainers.compose.DockerCompose("tests/fixtures") as compose:
        yield compose.get_service("redis", 6379)

@pytest.fixture
async def kafka_container():
    with testcontainers.compose.DockerCompose("tests/fixtures") as compose:
        yield compose.get_service("kafka", 9092)

# Component tests
async def test_page_fetcher_with_retry():
    # Test retry logic with mock server

async def test_ad_parser_extraction():
    # Test with sample HTML files

async def test_bloom_filter_persistence():
    # Test URL filtering and state persistence
```

**Sample Data**:
- Collected HTML snapshots from polovniautomobili.com
- Mock server responses for different scenarios
- Test data sets for various car makes/models

### Monitoring & Observability

**Prometheus Metrics**:
```python
# Per-component metrics
crawler_queue_size = Gauge('crawler_queue_size', 'URLs in crawl queue')
pages_fetched_total = Counter('pages_fetched_total', 'Total pages downloaded')
extraction_errors = Counter('extraction_errors', 'Failed extractions')
processing_duration = Histogram('processing_duration_seconds', 'Processing time')

# Business metrics
active_ads_total = Gauge('active_ads_total', 'Currently active ads')
avg_car_price = Gauge('avg_car_price_eur', 'Average car price')
popular_makes = Gauge('popular_makes', 'Popular car makes', ['make'])
```

**Structured Logging**:
```python
# JSON log format
{
    "timestamp": "2024-01-15T10:30:00Z",
    "level": "INFO",
    "component": "page_fetcher",
    "message": "Page fetched successfully",
    "url": "https://www.polovniautomobili.com/auto-oglasi/123456",
    "response_time_ms": 450,
    "cache_hit": false
}
```

**Grafana Dashboards**:
1. **System Overview**: Component health and resource usage
2. **Data Pipeline**: Throughput, latency, error rates
3. **Business Intelligence**: Market trends, pricing analytics
4. **Operational**: Queue sizes, processing delays

## Implementation Phases

### Phase 1: Foundation (Week 1)
- [x] Project structure creation
- [x] Docker Compose infrastructure
- [x] Shared models and utilities
- [x] CI/CD pipeline setup

### Phase 2: Core Crawling (Week 2)
- [ ] Crawler Scheduler implementation
- [ ] Page Fetcher with caching
- [ ] URL Extractor with pattern matching
- [ ] Basic monitoring setup

### Phase 3: Data Processing (Week 3)
- [ ] Ad Parser with versioning
- [ ] URL Filter with Bloom filter
- [ ] Ad Monitor scheduling
- [ ] Kafka topic setup and testing

### Phase 4: Analytics Pipeline (Week 4)
- [ ] Apache Flink job development
- [ ] PostgreSQL schema creation
- [ ] Stream processing logic
- [ ] Data aggregation testing

### Phase 5: Query Interface (Week 5)
- [ ] Query Service MCP implementation
- [ ] Chat API development
- [ ] Natural language processing
- [ ] API testing and documentation

### Phase 6: Integration & Testing (Week 6)
- [ ] End-to-end integration testing
- [ ] Performance optimization
- [ ] Monitoring dashboards
- [ ] Documentation completion

## Success Criteria

### Performance Targets
- **Crawling**: 10,000+ pages per day
- **Processing**: Real-time event processing (<5 min latency)
- **Query Response**: <2 seconds for analytics queries
- **Uptime**: 99% availability for all services

### Quality Metrics
- **Test Coverage**: 80% minimum
- **Type Safety**: Full pyright compliance
- **Error Rate**: <1% for all components
- **Data Accuracy**: >95% successful ad parsing

### Operational Requirements
- **Monitoring**: Full observability with Prometheus/Grafana
- **Logging**: Structured JSON logs for all components
- **Configuration**: Environment-based configuration
- **Documentation**: API docs and component specifications

## Component Development Guidelines

When implementing each component:

1. **Create component specification** following template
2. **Define clear interfaces** (input/output schemas)
3. **Implement checkpoint mechanism** for state recovery
4. **Add comprehensive logging** with structured format
5. **Include Prometheus metrics** for monitoring
6. **Write unit and integration tests** with testcontainers
7. **Document configuration options** and defaults
8. **Plan for horizontal scaling** (design only)

## Future Enhancements

### Scalability Improvements
- Horizontal scaling with Kafka consumer groups
- Load balancing for Chat API
- Database read replicas for analytics

### Feature Extensions
- Multiple car websites support
- Price prediction models
- User notification system
- API rate limiting and authentication

### Operational Enhancements
- ELK stack for log aggregation
- Automated backup strategies
- Health check improvements
- Performance optimization

---

This implementation plan serves as the complete blueprint for the Otto project. Each component should be developed following these specifications, with detailed planning sessions for complex components before implementation begins.