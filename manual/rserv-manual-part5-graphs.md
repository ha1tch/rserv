## rserv: A Versatile Prototyping Tool - Part 5: Graph Database Features with Sulpher

This section focuses on rserv's capabilities as a graph database, exploring its powerful graph querying features using the Sulpher query language. We'll examine how Sulpher enables complex traversals across relationships, filters based on node and relationship properties, and provides basic aggregation functions. We'll also include examples of how to create the graph structure, and then how to query it using Sulpher.

### 1. Graph Querying with Sulpher

rserv's Sulpher query language is specifically designed to enable you to interact with your data as a graph.  This allows you to efficiently explore relationships between entities and perform complex queries.

**Important Note:** rserv's graph functionality is built on top of its file-based storage system. It's not a dedicated graph database like Neo4j or Amazon Neptune.  As a result, its performance and scalability for large and complex graphs may be limited. 

### 2. Sulpher Query Syntax

Sulpher queries have a concise syntax for expressing graph traversals and filtering:

**Basic Structure:**

```cypher
(BFS | DFS) MATCH <path pattern> [WHERE <conditions>] RETURN <items>
```

**Components:**

* **`BFS` (Breadth-First Search):** Explores the graph level by level, finding all nodes at a given distance from the starting node before moving to the next level.
* **`DFS` (Depth-First Search):** Explores as deeply as possible along each path before backtracking.
* **`MATCH`:** Defines the path pattern to traverse across relationships.
* **`WHERE`:** Specifies conditions to filter the results based on node or relationship properties.
* **`RETURN`:**  Specifies the items to return in the result.

**Path Patterns:**

- **Nodes:** `(<variable name>[:<node type>][{<property1>:<value1>,<property2>:<value2>}])`
- **Relationships:** `-\[<relationship type>[:<relationship type>][{<property1>:<value1>,<property2>:<value2>}]->`

**Example Query:**

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User) WHERE user.name = 'Alice' RETURN friend.name
```

This query finds all friends of the user named "Alice" and returns their names.

### 3.  Creating the Graph Structure

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

# Python Example
import requests

def create_node(entity, data):
    url = f"http://localhost:9090/api/v1/{entity}"
    response = requests.post(url, json=data)
    return response.json()

alice_data = {"name": "Alice", "email": "alice@example.com", "age": 30}
bob_data = {"name": "Bob", "email": "bob@example.com", "age": 25}
charlie_data = {"name": "Charlie", "email": "charlie@example.com", "age": 32}
london_data = {"name": "London"}
python_data = {"name": "Python"}
java_data = {"name": "Java"}
post_data = {"title": "My First Post", "content": "This is the first post!"}

alice = create_node("users", alice_data)
bob = create_node("users", bob_data)
charlie = create_node("users", charlie_data)
london = create_node("cities", london_data)
python = create_node("skills", python_data)
java = create_node("skills", java_data)
post = create_node("posts", post_data)
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

# Bob wrote a post
curl -X PUT http://localhost:9090/api/v1/users/2 -H "Content-Type: application/json" -d '{"name": "Bob", "email": "bob@example.com", "age": 25, "friends": [{"id": 1}], "skills": [{"id": 5}], "wrote": [{"id": 6}]}'

# Alice wrote a post
curl -X PUT http://localhost:9090/api/v1/users/1 -H "Content-Type: application/json" -d '{"name": "Alice", "email": "alice@example.com", "age": 30, "friends": [{"id": 2}], "lives_in": {"id": 3}, "skills": [{"id": 4}], "wrote": [{"id": 7}]}'

# Python Example
import requests

def update_node(entity, id, data):
    url = f"http://localhost:9090/api/v1/{entity}/{id}"
    response = requests.put(url, json=data)
    return response.json()

# Alice is friends with Bob
alice_update = {"name": "Alice", "email": "alice@example.com", "age": 30, "friends": [{"id": 2}]}
update_node("users", 1, alice_update)

# Bob is friends with Alice
bob_update = {"name": "Bob", "email": "bob@example.com", "age": 25, "friends": [{"id": 1}]}
update_node("users", 2, bob_update)

# Alice lives in London
alice_update = {"name": "Alice", "email": "alice@example.com", "age": 30, "friends": [{"id": 2}], "lives_in": {"id": 3}}
update_node("users", 1, alice_update)

# Charlie lives in London
charlie_update = {"name": "Charlie", "email": "charlie@example.com", "age": 32, "lives_in": {"id": 3}}
update_node("users", 3, charlie_update)

# Alice has Python skill
alice_update = {"name": "Alice", "email": "alice@example.com", "age": 30, "friends": [{"id": 2}], "lives_in": {"id": 3}, "skills": [{"id": 4}]}
update_node("users", 1, alice_update)

# Bob has Java skill
bob_update = {"name": "Bob", "email": "bob@example.com", "age": 25, "friends": [{"id": 1}], "skills": [{"id": 5}]}
update_node("users", 2, bob_update)

# Bob wrote a post
bob_update = {"name": "Bob", "email": "bob@example.com", "age": 25, "friends": [{"id": 1}], "skills": [{"id": 5}], "wrote": [{"id": 6}]}
update_node("users", 2, bob_update)

# Alice wrote a post
alice_update = {"name": "Alice", "email": "alice@example.com", "age": 30, "friends": [{"id": 2}], "lives_in": {"id": 3}, "skills": [{"id": 4}], "wrote": [{"id": 7}]}
update_node("users", 1, alice_update)
```

### 3.  Sulpher Query Examples

Once you've created your graph structure, you can use Sulpher to perform queries.

#### 3.1.  Finding Friends of Friends (Up to Two Hops)

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User)-[:FRIENDS]->(friend_of_friend:User)
WHERE user.name = 'Alice'
RETURN friend_of_friend.name
```

This query finds all friends of Alice's friends (up to two hops). 

#### 3.2.  Finding Posts Written by Users in a Specific City

```cypher
MATCH (user:User)-[:LIVES_IN]->(city:City {name: 'London'})-[:WROTE]->(post:Post)
RETURN post.title
```

This query finds all posts written by users who live in London.

#### 3.3.  Counting Friends of a User

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User)
WHERE user.name = 'Alice'
RETURN COUNT(friend) AS num_friends
```

This query counts the number of friends that Alice has.

#### 3.4. Finding Users with Mutual Friends

```cypher
MATCH (user1:User)-[:FRIENDS]->(mutualFriend:User)-[:FRIENDS]->(user2:User)
WHERE user1.name = 'Alice' AND user2.name = 'Bob'
RETURN user1.name, user2.name, mutualFriend.name 
```

This query finds users who share a mutual friend. 

#### 3.5. Finding Users with a Specific Skill Set

```cypher
MATCH (user:User)-[:HAS_SKILL]->(skill:Skill {name: 'Python'})
RETURN user.name, user.email
```

This query finds users with the skill "Python."

#### 3.6. Finding the Most Popular City among Friends (Up to 3 Hops)

```cypher
MATCH (user:User)-[:FRIENDS*3]->(friend:User)-[:LIVES_IN]->(city:City)
WHERE user.name = 'Alice'
RETURN city.name, COUNT(city) AS popularity
ORDER BY popularity DESC
LIMIT 1
```

This query finds the city with the highest number of friends living there, among Alice's friends (up to three hops). 

#### 3.7. Finding Users with Multiple Skills

```cypher
MATCH (user:User)-[:HAS_SKILL]->(skill1:Skill {name: 'Python'})-[:AND]->(skill2:Skill {name: 'Java'})
RETURN user.name, user.email
```

This query finds users with both "Python" and "Java" skills.

#### 3.8. Finding Users with No Friends

```cypher
MATCH (user:User)
WHERE NOT (user)-[:FRIENDS]->()
RETURN user.name
```

This query finds users who have no friends.

#### 3.9. Finding Users with More Than 5 Friends

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User)
WHERE user.name = 'Alice'
WITH user, COUNT(friend) AS friendCount
WHERE friendCount > 5
RETURN user.name, friendCount
```

This query finds users with more than 5 friends.

#### 3.10. Calculating the Average Age of Friends

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User)
WHERE user.name = 'Alice'
RETURN AVG(friend.age) AS average_age_of_friends
```

This query calculates the average age of Alice's friends.

#### 3.11. Finding the Total Number of Posts Written by Friends

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User)-[:WROTE]->(post:Post)
WHERE user.name = 'Alice'
RETURN COUNT(post) AS total_posts_by_friends
```

This query counts the total number of posts written by Alice's friends.

#### 3.12. Finding the Average Number of Friends per User

```cypher
MATCH (user:User)-[:FRIENDS]->(friend:User)
RETURN user.name, COUNT(friend) AS num_friends
WITH user.name, num_friends
RETURN AVG(num_friends) AS average_friends_per_user
```

This query finds the average number of friends each user has. 

### 4. Aggregation Functions

Sulpher supports basic aggregation functions:

* **`COUNT`:**  Counts the number of matched items.
* **`SUM`:** Calculates the sum of numeric values.
* **`AVG`:**  Calculates the average of numeric values.

### 5.  Enabling Graph Querying

To enable graph querying in rserv:

* **Set the `graph_enabled` configuration option to `true`.** 

### 6.  Graph Query Endpoints

* **`/api/v1/graph/query`:**  Create a new graph query using a Sulpher query string.
* **`/api/v1/graph/query/<query_id>`:**  Retrieve the status of a graph query.
* **`/api/v1/graph/query/<query_id>/result`:**  Retrieve the results of a completed graph query.

### 7.  Example API Usage

```bash
# Create a graph query
curl -X POST http://localhost:9090/api/v1/graph/query -H "Content-Type: application/json" -d '{"query": "MATCH (user:User)-[:FRIENDS]->(friend:User) WHERE user.name = 'Alice' RETURN friend.name"}'

# Python Example
import requests

def execute_sulpher_query(query):
    url = "http://localhost:9090/api/v1/graph/query"
    response = requests.post(url, json={"query": query})
    query_id = response.json()["id"]
    status_url = f"http://localhost:9090/api/v1/graph/query/{query_id}"
    results_url = f"http://localhost:9090/api/v1/graph/query/{query_id}/result"

    while True:
        status_response = requests.get(status_url)
        if status_response.json()["status"] == "COMPLETED":
            results_response = requests.get(results_url)
            return results_response.json()["results"]
        time.sleep(0.5)

# Example Sulpher query
query = """
MATCH (user:User)-[:FRIENDS]->(friend:User)
WHERE user.name = 'Alice'
RETURN friend.name
"""

results = execute_sulpher_query(query)
print(results)

# Retrieve the status of the query (query ID is returned in the response of the previous request)
curl http://localhost:9090/api/v1/graph/query/1234567890

# Python Example
import requests

def get_query_status(query_id):
    url = f"http://localhost:9090/api/v1/graph/query/{query_id}"
    response = requests.get(url)
    return response.json()

query_id = 1234567890
status = get_query_status(query_id)
print(status)

# Get the results of the completed query
curl http://localhost:9090/api/v1/graph/query/1234567890/result

# Python Example
import requests

def get_query_results(query_id):
    url = f"http://localhost:9090/api/v1/graph/query/{query_id}/result"
    response = requests.get(url)
    return response.json()["results"]

results = get_query_results(query_id)
print(results)
```

### 8.  Summary

rserv's Sulpher query language provides powerful capabilities for exploring relationships within your data. It allows you to express complex graph traversals, filters, and aggregations efficiently. While rserv is not a dedicated graph database, Sulpher offers a valuable tool for prototyping and experimenting with graph-based applications. 

Remember that rserv's graph capabilities are best suited for small-scale graphs, and you should be aware of potential performance limitations when handling large and complex graph data. 





