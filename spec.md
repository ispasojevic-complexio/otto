# Otto high level spec
This file contains high level specification for "Otto" project.
Otto is a software platform that collects information about car sales via web crawling and provides analytics about car sales in real time via an AI assistant.
In the end Otto should be able to answer questions like:
- What cars are most easily sold?
- Which car makes depriciate in value?
- Are there new good deals?
- What is fair value for make X, model Y, year Z?
## Why is Otto being built?
Otto is a side project that aims to demonstrate my experience and capabilities as a software engineer. It aims to showcase a mixture of what what systems I've built before and the kind I'd like to build in the future.
This is aimed to be provided with my CV in future job hunts and potentially be turned into a product one day but for now this is out of scope.
As such the project should demonstrate good architectual thinking but still be able to be ran on a single machine to showcase "get stuff done" attitude. It should show good practices for a backend software engineer, great quality Python code with best practices like testing, documentation, type checking and usage of common tools like Docker, observability and logging.
## Project and spec organization
This file will contain high level overview of the architecture and list all the components.
There is also an architecture diagram in root folder Otto.drawio (https://app.diagrams.net/#G1Jqd1F6O2Bkr-Ix4OlrqljZaFNjURMvOf#%7B%22pageId%22%3A%22T_TweZ6uEtLprtYDqWzc%22%7D)
Detailed specification for each component can be found in spec.md file in each component folder.
## High level architecture
Otto is a mixture of web crawler, event drive system and AI chat bot.
To keep it simple we first crawl a single web site polovniautomobili.com (Serbian number 1. car ads platform).
We pass the data through an event driven data pipeline using logs, queues and caching.
In the end data is delivered to a Apache Flink app which provides near real time analytics which in form of data aggregations saved in PostgresSQL database.
In the end a user can interact with these analytics through a chat bot.
### Components
1. Crawler scheduler - Initially gets provided with seed urls and sends the URLs to be downloaded via a queue. Later it receives URLs from web crawling results for further crawling. Since this is a side project we can keep it quite simple.
2. Page fetcher + New page log - Downloads webpages, caches results if needed for more processing and sends new page events to page log
3. URL extractor - Finds all urls in a given page
4. Ad parser - Selects all relevant information from car ads. Make, model, price, year of production, mileage...
5. URL Filter - tracks seen ads. Filters out already processed pages and non polovniautomobili.com pages. Uses bloom filter for optimization
6. New ad log
7. Ad monitor - Cron job that checks when ad was removed or when price changed.
8. Stream processor
9. Query service MCP
10. chat API
### Tools used
1. Docker + Docker compose for containerization and service orcehstration
2. Apache Kafka for logs
3. Redis for queues
4. Redis for in memory caching
5. Apache Flink for data aggregation and analytics calculations
6. Postgres for storing analytics
7. Prometheus + Grafana for observability
8. Chat bot technology TBA
### Software development tools
1. Python as programming language
2. uv for dependency management
3. Pyrefly for type checking
4. Pydantic for seriazliation 
5. pytest, inline-snapshots and testcontainers for testing
6. Github actions for CI