
## Part 3: Graph Operations and Query Language

### 3.1 Introduction to Graph Capabilities

rserv 0.3.9 introduces powerful graph database capabilities, allowing you to model and query data based on relationships and connections. This is particularly useful for representing complex networks, social graphs, knowledge bases, and other interconnected data. 

Think of a graph database as a network of nodes (representing entities) connected by edges (representing relationships between entities).  

rserv's graph features provide a flexible way to:

* **Model Complex Relationships:**  Represent interconnected data with ease.
* **Perform Efficient Traversal:**  Query data by following relationships and connections.
* **Analyze Network Structures:**  Gain insights into the relationships and patterns within your data.

### 3.2 Sulpher Query Language

rserv uses a specialized query language called **Sulpher** for interacting with graph data.  Sulpher is designed to be intuitive and powerful, allowing you to express complex graph queries concisely.

#### 3.2.1 Basic Query Structure

A Sulpher query typically follows this structure:

```
(Algorithm) MATCH (Pattern) WHERE (Conditions) RETURN (Items)
```

* **Algorithm:**  This part specifies the graph traversal algorithm to use.  You can choose between:
    * `BFS` (Breadth-First Search):  Explores the graph level-by-level, starting from a specific node.
    * `DFS` (Depth-First Search):  Explores the graph by following a single path as far as possible before backtracking. 
* **Pattern:**  This part defines the pattern of nodes and relationships to match.  You can specify node types, properties, and relationships.
* **Conditions:** This part applies conditions to filter the results based on node properties.
* **Items:**  This part specifies the data to be returned (nodes, properties, or aggregations).

#### 3.2.2 Pattern Matching

You can use the `MATCH` clause to define patterns for nodes and relationships.  

* **Nodes:**  
    * **Type:**  Specify the type of node to match using the format `(variable:type)`.  
    * **Properties:**  Specify conditions for properties using the format `(variable:type{prop1:value1,prop2:value2})`
* **Relationships:**
    * **Type:**  Specify the relationship type using the format `-[:relationship_type]->`. 
    * **Properties:**  Specify conditions for relationship properties using the format `-[:relationship_type{rel_prop1:value1,rel_prop2:value2}]->`

**Example:**

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User) WHERE user.name = 'Alice' RETURN friend.name
```

This query finds all friends of the user named "Alice" and returns their names.

### 3.3 Creating the Graph Structure

Before you can query a graph in rserv, you need to create the nodes and edges (relationships) that make up your graph structure. You achieve this through the standard rserv CRUD operations and the `REF` type in your schema definition.

**Example Schema:**

```json
{
  "entities": {
    "users": {
      "fields": {
        "name": {"type": "string", "required": true},
        "email": {"type": "string", "required": true},
        "age": {"type": "integer", "required": false},
        "friends": {"type": "REF", "entity": "users", "field": "id"} 
      }
    },
    "cities": {
      "fields": {
        "name": {"type": "string", "required": true} 
      }
    },
    "posts": {
      "fields": {
        "title": {"type": "string", "required": true},
        "content": {"type": "string", "required": true}
      }
    },
    "skills": {
      "fields": {
        "name": {"type": "string", "required": true}
      }
    }
  }
}
```

**Creating Nodes:**

* You create nodes by creating documents within your entities using the `POST /api/v1/<entity>` endpoint. 

**Example (Create Users, Cities, Posts, and Skills):**

```bash
# Create Alice
curl -X POST http://localhost:9090/api/v1/users -H "Content-Type: application/json" -d '{"name": "Alice", "email": "alice@example.com", "age": 30}'

# Create Bob
curl -X POST http://localhost:9090/api/v1/users -H "Content-Type: application/json" -d '{"name": "Bob", "email": "bob@example.com", "age": 25}'

# Create Charlie
curl -X POST http://localhost:9090/api/v1/users -H "Content-Type: application/json" -d '{"name": "Charlie", "email": "charlie@example.com", "age": 32}'

# Create London
curl -X POST http://localhost:9090/api/v1/cities -H "Content-Type: application/json" -d '{"name": "London"}' 

# Create Python Skill
curl -X POST http://localhost:9090/api/v1/skills -H "Content-Type: application/json" -d '{"name": "Python"}' 

# Create Java Skill
curl -X POST http://localhost:9090/api/v1/skills -H "Content-Type: application/json" -d '{"name": "Java"}' 

# Create a post
curl -X POST http://localhost:9090/api/v1/posts -H "Content-Type: application/json" -d '{"title": "My First Post", "content": "This is the first post!"}'
```

**Creating Relationships (Edges):**

* You create edges by referencing other documents within your document using the `REF` type.

**Example (Create Friendships, Locations, and Skills):**

```bash
# Alice is friends with Bob
curl -X PUT http://localhost:9090/api/v1/users/1 -H "Content-Type: application/json" -d '{"name": "Alice", "email": "alice@example.com", "age": 30, "friends": [{"id": 2}]}'

# Bob is friends with Alice
curl -X PUT http://localhost:9090/api/v1/users/2 -H "Content-Type: application/json" -d '{"name": "Bob", "email": "bob@example.com", "age": 25, "friends": [{"id": 1}]}'

# Alice lives in London
curl -X PUT http://localhost:9090/api/v1/users/1 -H "Content-Type: application/json" -d '{"name": "Alice", "email": "alice@example.com", "age": 30, "friends": [{"id": 2}], "lives_in": {"id": 3}}'

# Charlie lives in London
curl -X PUT http://localhost:9090/api/v1/users/3 -H "Content-Type: application/json" -d '{"name": "Charlie", "email": "charlie@example.com", "age": 32, "lives_in": {"id": 3}}'

# Alice has Python skill
curl -X PUT http://localhost:9090/api/v1/users/1 -H "Content-Type: application/json" -d '{"name": "Alice", "email": "alice@example.com", "age": 30, "friends": [{"id": 2}], "lives_in": {"id": 3}, "skills": [{"id": 4}]}'

# Bob has Java skill
curl -X PUT http://localhost:9090/api/v1/users/2 -H "Content-Type: application/json" -d '{"name": "Bob", "email": "bob@example.com", "age": 25, "friends": [{"id": 1}], "skills": [{"id": 5}]}'
```

### 3.4  Sulpher Query Examples

Once you've created your graph structure, you can use Sulpher to perform queries.

**Example 1: Finding Friends of Friends (Up to Two Hops)**

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User)-[:FRIENDS]->(friend_of_friend:User)
WHERE user.name = 'Alice'
RETURN friend_of_friend.name
```

**Example 2: Finding Posts Written by Users in a Specific City**

```cypher
MATCH (user:User)-[:LIVES_IN]->(city:City {name: 'London'})-[:WROTE]->(post:Post)
RETURN post.title
```

**Example 3: Counting Friends of a User**

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User)
WHERE user.name = 'Alice'
RETURN COUNT(friend) AS num_friends
```

**Example 4: Finding Users with Mutual Friends**

```cypher
MATCH (user1:User)-[:FRIENDS]->(mutualFriend:User)-[:FRIENDS]->(user2:User)
WHERE user1.name = 'Alice' AND user2.name = 'Bob'
RETURN user1.name, user2.name, mutualFriend.name 
```

**Example 5: Finding Users with a Specific Skill Set**

```cypher
MATCH (user:User)-[:HAS_SKILL]->(skill:Skill {name: 'Python'})
RETURN user.name, user.email
```

**Example 6: Finding the Most Popular City among Friends (Up to 3 Hops)**

```cypher
MATCH (user:User)-[:FRIENDS*3]->(friend:User)-[:LIVES_IN]->(city:City)
WHERE user.name = 'Alice'
RETURN city.name, COUNT(city) AS popularity
ORDER BY popularity DESC
LIMIT 1
```

**Example 7: Finding Users with Multiple Skills**

```cypher
MATCH (user:User)-[:HAS_SKILL]->(skill1:Skill {name: 'Python'})-[:AND]->(skill2:Skill {name: 'Java'})
RETURN user.name, user.email
```

**Example 8: Finding Users with No Friends**

```cypher
MATCH (user:User)
WHERE NOT (user)-[:FRIENDS]->()
RETURN user.name
```

**Example 9: Finding Users with More Than 5 Friends**

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User)
WHERE user.name = 'Alice'
WITH user, COUNT(friend) AS friendCount
WHERE friendCount > 5
RETURN user.name, friendCount
```

**Example 10: Calculating the Average Age of Friends**

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User)
WHERE user.name = 'Alice'
RETURN AVG(friend.age) AS average_age_of_friends
```

**Example 11: Finding the Total Number of Posts Written by Friends**

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User)-[:WROTE]->(post:Post)
WHERE user.name = 'Alice'
RETURN COUNT(post) AS total_posts_by_friends
```

**Example 12: Finding the Average Number of Friends per User**

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User)
RETURN user.name, COUNT(friend) AS num_friends
WITH user.name, num_friends
RETURN AVG(num_friends) AS average_friends_per_user
```

### 3.5  Graph API Endpoints

The rserv graph API provides endpoints for creating, retrieving, and managing graph queries:

#### 3.5.1 Creating Graph Queries

**Method:** POST

**Endpoint:** `/api/v1/graph/query`

**Body:**

* **query:** The Sulpher query string.
* **max_depth:**  (Optional) The maximum depth to traverse the graph.  Default: 10.

**Response:**

* **202 Accepted:** The query is accepted for asynchronous execution. The response body will include a unique query ID (`query_id`).
* **400 Bad Request:**  If the query is invalid or malformed.
* **200 OK:** (If the query is found in the cache, it will be immediately executed and the result returned).

**Example:**

```bash
curl -X POST http://localhost:9090/api/v1/graph/query -H "Content-Type: application/json" -d '{"query": "MATCH (u:User) WHERE u.id = 1 MATCH p = (u)-[*]->(n) RETURN n"}'
```

**Python:**

```python
import requests
requests.post('http://localhost:9090/api/v1/graph/query', json={"query": "MATCH (u:User) WHERE u.id = 1 MATCH p = (u)-[*]->(n) RETURN n"})
```

#### 3.5.2 Retrieving Query Status

**Method:** GET

**Endpoint:** `/api/v1/graph/query/<query_id>`

**Response:**

* **200 OK:**  The response body will include the status of the query (`pending`, `completed`, or `failed`). 
* **404 Not Found:** The query with the specified `query_id` does not exist.

**Example:**

```bash
curl http://localhost:9090/api/v1/graph/query/your_query_id_here
```

**Python:**

```python
import requests
requests.get('http://localhost:9090/api/v1/graph/query/your_query_id_here').json()
```

#### 3.5.3 Retrieving Query Results

**Method:** GET

**Endpoint:** `/api/v1/graph/query/<query_id>/result`

**Response:**

* **200 OK:** The response body will include the results of the query, formatted as a list of dictionaries, along with execution statistics. 
* **404 Not Found:** The query with the specified `query_id` does not exist.
* **400 Bad Request:** The query has not yet completed.

**Example:**

```bash
curl http://localhost:9090/api/v1/graph/query/your_query_id_here/result
```

**Python:**

```python
import requests
requests.get('http://localhost:9090/api/v1/graph/query/your_query_id_here/result').json()
```

### 3.6 Aggregation Functions

Sulpher supports basic aggregation functions:

* **`COUNT`:**  Counts the number of matched items.
* **`SUM`:** Calculates the sum of numeric values.
* **`AVG`:**  Calculates the average of numeric values.

**Example:**

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User)
WHERE user.name = 'Alice'
RETURN COUNT(friend) AS num_friends
```

This query counts the number of friends that Alice has.

### 3.7 Enabling Graph Querying

To enable graph querying in rserv:

* **Set the `graph_enabled` configuration option to `true`.** 

**Example:**

```bash
python rserv.py --graph_enabled True
```

### 3.8 Summary

rserv's Sulpher query language provides powerful capabilities for exploring relationships within your data. It allows you to express complex graph traversals, filters, and aggregations efficiently. While rserv is not a dedicated graph database, Sulpher offers a valuable tool for prototyping and experimenting with graph-based applications. 

Remember that rserv's graph capabilities are best suited for small-scale graphs, and you should be aware of potential performance limitations when handling large and complex graph data. 

**Next Steps:**

* **Part 4:  Advanced Graph Operations:**  Learn about additional graph operations, such as shortest paths, common neighbors, and node degree.
* **Part 5:  Full-Text Search and Caching:**  Explore how to search for documents and utilize caching for performance improvements. 

---

