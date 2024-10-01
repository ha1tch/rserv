
# rserv: A Versatile Prototyping Tool  
### Part 5: Graph Database Features with Sulpher

This section explores **rserv's** capabilities as a graph database, focusing on its graph querying features using the **Sulpher** query language. We'll discuss how Sulpher enables complex traversals across relationships, filters based on node and relationship properties, and supports basic aggregation functions. Examples will show how to create graph structures and query them using Sulpher.

---

### 1. Graph Querying with Sulpher

**rserv's Sulpher** query language lets you interact with data as a graph, enabling the exploration of relationships between entities and performing complex queries.

> **Note**: rserv's graph functionality is built on top of a file-based storage system, not a dedicated graph database (e.g., Neo4j or Amazon Neptune). This may limit performance and scalability for large, complex graphs.

---

### 2. Sulpher Query Syntax

Sulpher offers a concise syntax for graph traversals and filtering.

**Basic Structure**:

```
(BFS | DFS) MATCH <path pattern> [WHERE <conditions>] RETURN <items>
```

**Components**:
- **BFS**: Breadth-First Search, explores graph level by level.
- **DFS**: Depth-First Search, explores deeply along each path.
- **MATCH**: Defines the path pattern.
- **WHERE**: Filters results by node or relationship properties.
- **RETURN**: Specifies the output items.

**Path Patterns**:
- **Nodes**: `(variable_name[:node_type][{property1: value1, property2: value2}])`
- **Relationships**: `-[relationship_type[:relationship_type][{property1: value1, property2: value2}]]->`

**Example Query**:

```sql
MATCH (user:User)-[:FRIENDS]->(friend:User)
WHERE user.name = 'Alice'
RETURN friend.name
```
This finds all friends of the user named Alice and returns their names.

---

### 3. Creating the Graph Structure

Before querying, you need to create the nodes and edges of your graph using rserv's CRUD operations and the `REF` type in your schema.

**Example Schema**:

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

**Creating Nodes**:  
Nodes are created through the POST endpoint `/api/v1/<entity>`.

**Example**:

```bash
# Create Alice
curl -X POST http://localhost:9090/api/v1/users -H "Content-Type: application/json" -d '{"name": "Alice", "email": "alice@example.com", "age": 30}'
```

Python Example:

```python
import requests

def create_node(entity, data):
    url = f"http://localhost:9090/api/v1/{entity}"
    response = requests.post(url, json=data)
    return response.json()

alice_data = {"name": "Alice", "email": "alice@example.com", "age": 30}
alice = create_node("users", alice_data)
```

---

### 4. Creating Relationships (Edges)

Edges are created by referencing other documents in your document using the `REF` type.

**Example**:

```bash
# Alice is friends with Bob
curl -X PUT http://localhost:9090/api/v1/users/1 -H "Content-Type: application/json" -d '{"friends": [{"id": 2}]}'
```

Python Example:

```python
def update_node(entity, id, data):
    url = f"http://localhost:9090/api/v1/{entity}/{id}"
    response = requests.put(url, json=data)
    return response.json()

alice_update = {"friends": [{"id": 2}]}
update_node("users", 1, alice_update)
```

---

### 5. Sulpher Query Examples

Once the graph structure is created, you can perform queries using **Sulpher**.

#### 5.1 Finding Friends of Friends (Up to Two Hops)
```sql
MATCH (user:User)-[:FRIENDS]->(friend:User)-[:FRIENDS]->(friend_of_friend:User)
WHERE user.name = 'Alice'
RETURN friend_of_friend.name
```

#### 5.2 Finding Posts Written by Users in a Specific City
```sql
MATCH (user:User)-[:LIVES_IN]->(city:City {name: 'London'})-[:WROTE]->(post:Post)
RETURN post.title
```

#### 5.3 Counting Friends of a User
```sql
MATCH (user:User)-[:FRIENDS]->(friend:User)
WHERE user.name = 'Alice'
RETURN COUNT(friend) AS num_friends
```

#### 5.4 Finding Users with Mutual Friends
```cypher
MATCH (user1:User)-[:FRIENDS]->(mutualFriend:User)-[:FRIENDS]->(user2:User)
WHERE user1.name = 'Alice' AND user2.name = 'Bob'
RETURN mutualFriend.name
```

---

### 6. Aggregation Functions

Sulpher supports basic aggregation functions:
- **COUNT**: Counts the number of matched items.
- **SUM**: Sums numeric values.
- **AVG**: Calculates the average of numeric values.

---

### 7. Enabling Graph Querying

To enable graph querying in rserv:
1. Set `graph_enabled` configuration option to `true`.

**Graph Query Endpoints**:
- `/api/v1/graph/query`: Create a new query.
- `/api/v1/graph/query/<query_id>`: Retrieve the status of a query.
- `/api/v1/graph/query/<query_id>/result`: Get the results of a completed query.

**Example**:

```bash
# Create a graph query
curl -X POST http://localhost:9090/api/v1/graph/query -H "Content-Type: application/json" -d '{"query": "MATCH (user:User)-[:FRIENDS]->(friend:User) WHERE user.name = 'Alice' RETURN friend.name"}'
```

---

### 8. Summary

**rserv's Sulpher** query language offers powerful graph-based querying capabilities, including traversal, filtering, and aggregation functions. While it's not a dedicated graph database, Sulpher provides a useful tool for prototyping graph-based applications on a small scale.

> Be mindful of performance limitations when handling large graphs in rserv.

---
