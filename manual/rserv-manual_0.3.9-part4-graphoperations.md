## Part 4:  Advanced Graph Operations

In addition to the basic graph query capabilities outlined in Part 3, rserv 0.3.9 provides a suite of advanced graph operations for analyzing and interacting with your data. These operations can be used to explore complex relationships, gain insights into network structures, and perform specialized tasks.

### 4.1 Shortest Path

The `shortestPath` operation allows you to find the shortest path between two nodes in your graph. This is useful for tasks such as:

* **Route Planning:** Finding the shortest path between two locations on a map.
* **Network Analysis:** Determining the most efficient communication path between nodes.
* **Recommendation Systems:**  Identifying the shortest path of relationships between users in a social network.

**Method:** POST

**Endpoint:** `/api/v1/graph/shortestPath`

**Body:**

* **start_node_id:** The ID of the starting node.
* **end_node_id:** The ID of the ending node.
* **max_depth:** (Optional)  The maximum depth to traverse the graph. Default: 10.

**Response:**

* **200 OK:** The response body will contain the shortest path between the specified nodes, represented as a list of nodes.
* **404 Not Found:**  No path found between the two nodes. 
* **400 Bad Request:** The request is malformed.

**Example:**

To find the shortest path between user nodes with IDs 1 and 5:

```bash
curl -X POST http://localhost:9090/api/v1/graph/shortestPath -H "Content-Type: application/json" -d '{"start_node_id": 1, "end_node_id": 5}'
```

**Python:**

```python
import requests
requests.post('http://localhost:9090/api/v1/graph/shortestPath', json={"start_node_id": 1, "end_node_id": 5})
```

### 4.2 Common Neighbors

The `commonNeighbors` operation helps you find nodes that share a common neighbor with a given node.  This is useful for:

* **Social Network Analysis:**  Identifying users with shared friends.
* **Knowledge Graph Exploration:** Discovering entities with similar relationships to a given entity.
* **Collaborative Filtering:**  Recommending items based on shared preferences. 

**Method:** POST

**Endpoint:** `/api/v1/graph/commonNeighbors`

**Body:**

* **node_id1:** The ID of the first node.
* **node_id2:** The ID of the second node.

**Response:**

* **200 OK:** The response body will contain a list of nodes that are common neighbors to the two specified nodes. 
* **400 Bad Request:** The request is malformed.

**Example:**

To find the common neighbors of user nodes with IDs 2 and 3:

```bash
curl -X POST http://localhost:9090/api/v1/graph/commonNeighbors -H "Content-Type: application/json" -d '{"node_id1": 2, "node_id2": 3}'
```

**Python:**

```python
import requests
requests.post('http://localhost:9090/api/v1/graph/commonNeighbors', json={"node_id1": 2, "node_id2": 3})
```

### 4.3 Node Degree

The `degree` operation allows you to retrieve the degree of a node in your graph. The degree represents the number of connections a node has. 

**Method:** GET

**Endpoint:** `/api/v1/graph/nodes/<node_id>/degree`

**Query Parameters:**

* **direction:** (Optional) The direction to consider (default: 'all').
    * `in`:  Count only incoming edges.
    * `out`: Count only outgoing edges. 
    * `all`: Count both incoming and outgoing edges (default).

**Response:**

* **200 OK:** The response body will contain the node's degree, as an integer.
* **404 Not Found:** The node with the specified `node_id` does not exist. 
* **400 Bad Request:** The request is malformed.

**Example:**

To retrieve the total degree of the user node with ID 10:

```bash
curl http://localhost:9090/api/v1/graph/nodes/10/degree
```

**Python:**

```python
import requests
requests.get('http://localhost:9090/api/v1/graph/nodes/10/degree').json()
```

To retrieve the in-degree of the user node with ID 10:

```bash
curl http://localhost:9090/api/v1/graph/nodes/10/degree?direction=in
```

**Python:**

```python
import requests
requests.get('http://localhost:9090/api/v1/graph/nodes/10/degree', params={"direction": "in"}).json()
```

### 4.4 Path Existence

The `pathExists` operation checks whether a path exists between two nodes in your graph, up to a specified maximum depth. This is useful for determining if there is a connection between two nodes, even if the exact path is not important.

**Method:** POST

**Endpoint:** `/api/v1/graph/pathExists`

**Body:**

* **start_node_id:** The ID of the starting node.
* **end_node_id:** The ID of the ending node.
* **max_depth:** (Optional)  The maximum depth to traverse the graph. Default: 10.

**Response:**

* **200 OK:** The response body will contain a boolean value indicating whether a path exists (`true` or `false`).
* **400 Bad Request:**  The request is malformed.

**Example:**

To check if a path exists between user nodes with IDs 1 and 7, with a maximum depth of 5:

```bash
curl -X POST http://localhost:9090/api/v1/graph/pathExists -H "Content-Type: application/json" -d '{"start_node_id": 1, "end_node_id": 7, "max_depth": 5}'
```

**Python:**

```python
import requests
requests.post('http://localhost:9090/api/v1/graph/pathExists', json={"start_node_id": 1, "end_node_id": 7, "max_depth": 5})
```

### 4.5 Neighborhood Aggregation

The `neighborhoodAggregate` operation allows you to perform aggregations on node properties within a node's neighborhood, up to a specified depth.  This is useful for:

* **Network Analysis:**  Calculating metrics for a node's immediate connections.
* **Recommendation Systems:**  Finding the average rating of items recommended by a user's friends.
* **Data Exploration:**  Exploring the distribution of values within a node's neighborhood.

**Method:** POST

**Endpoint:** `/api/v1/graph/nodes/neighborhoodAggregate`

**Body:**

* **node_id:** The ID of the node to examine.
* **depth:** (Optional)  The maximum depth to consider in the neighborhood. Default: 1.
* **property:** (Optional)  The name of the property to aggregate. Default: `id`.
* **aggregation:**  (Optional)  The aggregation function to apply (default: `count`). Supported functions:
    * `count`:  Count the number of nodes in the neighborhood.
    * `sum`:  Sum the values of the specified property in the neighborhood.
    * `avg`:  Calculate the average of the specified property in the neighborhood.

**Response:**

* **200 OK:** The response body will contain the result of the aggregation. 
* **404 Not Found:** The node with the specified `node_id` does not exist. 
* **400 Bad Request:** The request is malformed.

**Example:**

To calculate the average age of users within a depth of 2 from the user with ID 15:

```bash
curl -X POST http://localhost:9090/api/v1/graph/nodes/neighborhoodAggregate -H "Content-Type: application/json" -d '{"node_id": 15, "depth": 2, "property": "age", "aggregation": "avg"}'
```

**Python:**

```python
import requests
requests.post('http://localhost:9090/api/v1/graph/nodes/neighborhoodAggregate', json={"node_id": 15, "depth": 2, "property": "age", "aggregation": "avg"})
```

### 4.6 Graph Statistics

The `/api/v1/graph/statistics` endpoint provides a convenient way to retrieve overall statistics about your graph database:

**Method:** GET

**Endpoint:** `/api/v1/graph/statistics`

**Response:**

* **200 OK:** The response body will contain a dictionary of graph statistics, including:
    * **node_count:** The total number of nodes in the graph.
    * **edge_count:** The total number of edges (relationships) in the graph.
    * **avg_out_degree:**  The average out-degree of nodes in the graph.

**Example:**

```bash
curl http://localhost:9090/api/v1/graph/statistics
```

**Python:**

```python
import requests
requests.get('http://localhost:9090/api/v1/graph/statistics').json()
```

### 4.7 Graph Indexing (Optional)

rserv 0.3.9 offers optional support for indexed graph data structures. This means that rserv can build an inverted index of nodes and relationships, which can significantly improve performance when performing queries with specific node types or properties.  

**Enabling Indexing:**

To enable indexing, you need to set the `rserv_graph` configuration option to `'indexed'`:

```bash
python rserv.py --rserv_graph indexed
```

**How Indexing Works:**

The index is stored in a separate file (default: `graph.index`). When a query is executed, rserv can use the index to quickly retrieve a list of nodes that match the specified type or properties.  This significantly speeds up graph traversal compared to scanning through all nodes in the graph.

**Performance Impact:**

* **Improved Query Performance:** Indexing can significantly improve the speed of graph queries, especially for complex queries with filtering based on node types or properties.
* **Increased Memory Usage:** Maintaining the index requires additional memory.
* **Data Update Overhead:**  Updating the index can add overhead during document creation, update, and deletion operations.

**Note:** If your graph is very small or you are not performing queries that rely heavily on node types or properties, indexing might not provide a significant performance benefit.

**Next Steps:**

* **Part 5:  Full-Text Search and Caching:**  Explore how to search for documents and utilize caching for performance improvements. 

---


