## Part 5:  Full-Text Search and Caching

### 5.1 Full-Text Search

rserv 0.3.9 provides basic full-text search capabilities, allowing you to search for documents based on their content.  This can be useful for finding documents that contain specific keywords or phrases.

#### 5.1.1 Enabling Full-Text Search

To enable full-text search, you need to set the `fulltext_enabled` configuration option to `True`:

```bash
python rserv.py --fulltext_enabled True
```

When full-text search is enabled, rserv will automatically index the content of your documents.

#### 5.1.2 Search Endpoints

**Method:** GET

**Endpoint:** `/api/v1/<entity>/search`

**Query Parameters:**

* **query:** The search query string.
* **field:** (Optional) The specific field to search within.  Default: `name`.
* **page:** (Optional) The page number for paginated results. Default: 1.
* **per_page:** (Optional) The number of items to return per page. Default: configured `default_page_size`.
* **sort:** (Optional)  Sorting parameters (e.g., `field1:asc,field2:desc`).

**Response:**

* **200 OK:** The response body will contain a list of documents matching the search query, along with pagination metadata.
* **400 Bad Request:**  The request is malformed.

**Example:**

To search for user documents containing the keyword "John" in the `name` field:

```bash
curl "http://localhost:9090/api/v1/users/search?query=John&field=name"
```

**Python:**

```python
import requests
requests.get('http://localhost:9090/api/v1/users/search', params={"query": "John", "field": "name"}).json()
```

### 5.2 Caching

rserv includes caching functionality to improve the performance of frequently accessed data.  Caching stores copies of data in a faster storage system (like memory or a Redis server) so that subsequent requests for the same data can be served more quickly.

#### 5.2.1 Cache Configuration

rserv 0.3.9 offers two caching options:

* **TTLCache (Default):** An in-memory cache with a time-to-live (TTL) setting that automatically expires cached items after a specified duration. This is a good option for small-scale applications or when you don't have a Redis server available.
* **Redis Cache:** A more robust and scalable caching option using the Redis server. This is ideal for larger applications or for managing larger datasets that require a more persistent cache.

To configure the cache type, use the `cache_type` configuration option:

* **TTLCache:**

   ```bash
   python rserv.py --cache_type ttlcache
   ```

* **Redis Cache:**

   ```bash
   python rserv.py --cache_type redis
   ```

   For Redis caching, you also need to configure the Redis host and port using the `redis_host` and `redis_port` options:

   ```bash
   python rserv.py --cache_type redis --redis_host localhost --redis_port 6379 
   ```

#### 5.2.2 Cache Invalidation

rserv automatically invalidates cache entries after document creation, update, or deletion operations. This ensures that cached data remains consistent with the actual data stored in the database.

#### 5.2.3 Performance Impact

Caching can significantly improve the performance of your API, especially for frequently accessed data. It can reduce the number of file I/O operations and speed up response times.

#### 5.2.4 Cache TTL

The `cache_ttl` configuration option controls the time-to-live (TTL) for cached items. It specifies the duration for which a cached item remains valid.  

* **TTLCache:**  Cached items will automatically expire after the `cache_ttl` seconds have elapsed.
* **Redis Cache:**  You can set the TTL for individual keys when using the Redis cache.

**Example:**

To set the cache TTL to 300 seconds (5 minutes):

```bash
python rserv.py --cache_ttl 300
```

**Next Steps:**

* **Part 6:  Error Handling, Security, and Best Practices:**  Learn about error handling, security considerations, and best practices for working with rserv. 

---


