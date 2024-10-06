## Part 6: Error Handling, Best Practices

### 6.1 Error Handling

rserv employs a robust error handling system to provide informative feedback when errors occur during API requests. Here's a breakdown of common error types and corresponding status codes:

**Common Error Types:**

* **400 Bad Request:**  Indicates that the request is malformed or contains invalid data. This could occur due to:
    * **Missing Required Fields:**  A required field in the request body is missing.
    * **Invalid Data Types:**  A field value does not match the expected data type.
    * **Schema Validation Errors:**  The data in the request body violates the defined schema for the entity.
    * **Invalid Query Format:**  The Sulpher query provided is malformed or contains invalid syntax. 
    * **Invalid Foreign Key:**  A foreign key reference points to a non-existent document.
    * **Invalid Aggregation Function:**  An invalid aggregation function is specified in a neighborhood aggregation query.
    * **Invalid Sort Parameters:**  The sort parameters provided are not valid.
* **404 Not Found:**  Indicates that the requested resource (document, node, query, or entity) cannot be found.
* **409 Conflict:**  Indicates that a document with the specified ID already exists when attempting to create a new document with a custom ID.
* **500 Internal Server Error:**  Indicates a server-side error that prevented the request from being completed. This could be due to unexpected exceptions or issues in data access.

**Example Error Response:**

```json
{
  "error": {
    "message": "Missing required field: name",
    "status_code": 400
  },
  "_links": {
    "self": {
      "href": "http://localhost:9090/api/v1/users"
    }
  }
}
```

**Error Details:**

In many cases, the error response will include additional details to help you understand and resolve the issue.  For example:

* **Schema Validation Errors:**  The response body will list the specific fields that failed validation and the reasons.
* **Foreign Key Errors:**  The response body will indicate which foreign key constraint failed and the offending value. 
* **Sulpher Query Errors:** The response body may include details about the invalid syntax or missing parts of the query.

### 6.2 Best Practices

Here are some best practices for using rserv effectively:

**Data Modeling and Schema Design:**

* **Entity Organization:**  Divide your data into logical entities based on the relationships and properties you want to represent. 
* **Schema-less vs. Schema-Enforced:**  Consider whether a schema is necessary for your data.  A schema-less approach is good for rapid prototyping and when data structures are evolving.  A schema-enforced approach provides data consistency and validation.
* **Schema Definitions:**  When using a schema, define clear field types, required fields, and any applicable constraints.
* **Foreign Key Relationships:**  Use foreign keys to model relationships between entities, ensuring data integrity.
* **Unique Constraints:**  Apply unique constraints to fields that should have distinct values. 

**API Request Optimization:**

* **Caching:**  Leverage caching (TTLCache or Redis) to improve the performance of frequently accessed data.
* **Pagination:**  Use pagination for large datasets to avoid returning excessively large responses.
* **Filtering:**  Use the `WHERE` clause in Sulpher queries to filter results and retrieve only the data you need.
* **Depth Limits:**  Set appropriate depth limits for graph queries to control the amount of data traversed and prevent performance issues.

**Other Considerations:**

* **Data Storage:**  rserv stores data in JSON files.  You might need to consider data volume and how you will manage storage as your application grows. 
* **Full-Text Search:**  While rserv provides basic full-text search, consider using a dedicated search engine (like Elasticsearch) for more advanced search features and scalability.

By following these best practices, you can build efficient, reliable, and scalable API applications using rserv.


### 6.3 Blogging Application Example

Here's an example of how to model a blogging application using rserv's graph capabilities.

**Entities:**

* **Bloggers:**  Represents individual bloggers.
* **Blogs:**  Represents blogs created by bloggers.
* **Posts:**  Represents individual blog posts.
* **Tags:**  Represents keywords or categories associated with posts.
* **Comments:**  Represents comments made on blog posts.

**Relationships:**

* **CREATED_BY:**  A blogger can create multiple blogs.
* **PUBLISHED_IN:**  A post is published in a specific blog.
* **TAGGED_WITH:**  A post can be tagged with multiple tags.
* **COMMENTED_ON:** A comment is associated with a specific post.

**Example Data:**

```json
# Bloggers
{
  "id": 1,
  "name": "John Doe",
  "email": "john@example.com",
  "type": "Blogger"
}

# Blogs
{
  "id": 1,
  "title": "Tech Blog",
  "description": "Latest technology news and reviews.",
  "type": "Blog",
  "created_by": {"type": "REF", "entity": "Bloggers", "id": 1} 
}

# Posts
{
  "id": 1,
  "title": "Top 5 Programming Languages in 2023",
  "content": "A detailed analysis of the most popular programming languages...",
  "type": "Post",
  "published_in": {"type": "REF", "entity": "Blogs", "id": 1},
  "tagged_with": [
    {"type": "REF", "entity": "Tags", "id": 1},
    {"type": "REF", "entity": "Tags", "id": 2}
  ]
}

# Tags
{
  "id": 1,
  "name": "Programming",
  "type": "Tag"
}

# Comments
{
  "id": 1,
  "content": "Great article! I agree with your points.",
  "author": "Jane Smith",
  "commented_on": {"type": "REF", "entity": "Posts", "id": 1}
}
```

**Interesting Queries (Supported by rserv 0.3.9):**

1. **Find all posts published by a specific blogger:**

```
MATCH (b:Blogger) WHERE b.id = 1
MATCH (p:Post)-[:PUBLISHED_IN]->(bl:Blog)-[:CREATED_BY]->(b)
RETURN p
```

2. **Find all posts tagged with a specific tag:**

```
MATCH (t:Tag) WHERE t.name = "Programming"
MATCH (p:Post)-[:TAGGED_WITH]->(t)
RETURN p
```

3. **Find all comments made on a specific post:**

```
MATCH (p:Post) WHERE p.id = 1
MATCH (c:Comment)-[:COMMENTED_ON]->(p)
RETURN c
```

4. **Find all bloggers who have commented on a specific post:**

```
MATCH (p:Post) WHERE p.id = 1
MATCH (c:Comment)-[:COMMENTED_ON]->(p)
RETURN DISTINCT c.author
```

5. **Find all posts tagged with "Programming" that have been commented on by a specific blogger:**

```
MATCH (b:Blogger) WHERE b.id = 1
MATCH (p:Post)-[:TAGGED_WITH]->(t:Tag)
WHERE t.name = "Programming"
MATCH (c:Comment)-[:COMMENTED_ON]->(p)
WHERE c.author = b.name
RETURN p
```

6. **Find all posts that have been commented on by bloggers who have also created blogs tagged with "Programming":**

```
MATCH (b:Blogger)-[:CREATED_BY]->(bl:Blog)-[:PUBLISHED_IN]->(p1:Post)-[:TAGGED_WITH]->(t1:Tag)
WHERE t1.name = "Programming"
MATCH (b)-[:CREATED_BY]->(bl)-[:PUBLISHED_IN]->(p2:Post)-[:COMMENTED_ON]->(c:Comment)
RETURN p2 
```

**New Supported Sulpher Queries:**

1. **Find all bloggers who have created blogs with at least 3 posts:**

   ```sulpher
   MATCH (b:Blogger)-[:CREATED_BY]->(bl:Blog)-[:PUBLISHED_IN]->(p:Post)
   WITH b, count(p) AS post_count
   WHERE post_count >= 3
   RETURN b, post_count
   ```

2. **Find all posts that have been commented on by bloggers who have also created blogs with the same title:**

   ```sulpher
   MATCH (b:Blogger)-[:CREATED_BY]->(bl1:Blog)-[:PUBLISHED_IN]->(p1:Post)
   MATCH (b)-[:CREATED_BY]->(bl2:Blog)-[:PUBLISHED_IN]->(p2:Post)-[:COMMENTED_ON]->(c:Comment)
   WHERE bl1.title = bl2.title
   RETURN p1
   ```

3. **Find all posts that have been commented on by bloggers who have also commented on the same post:**

   ```sulpher
   MATCH (b:Blogger)-[:COMMENTED_ON]->(c1:Comment)-[:COMMENTED_ON]->(p1:Post)
   MATCH (b)-[:COMMENTED_ON]->(c2:Comment)-[:COMMENTED_ON]->(p2:Post)
   WHERE p1.id = p2.id
   RETURN DISTINCT p1
   ```

4. **Find all posts that have been tagged with "Programming" and published in blogs created by bloggers with more than 100 followers:**

   ```sulpher
   MATCH (b:Blogger)-[:CREATED_BY]->(bl:Blog)-[:PUBLISHED_IN]->(p:Post)-[:TAGGED_WITH]->(t:Tag)
   WHERE t.name = "Programming" AND b.followers > 100
   RETURN p
   ```

**Python Code for Creating the Blogging Graph (using rserv API):**

```python
import requests

# 1. API Base URL
base_url = 'http://localhost:9090/api/v1'

# 2. Create Bloggers
def create_blogger(name, email):
    url = f'{base_url}/Bloggers'
    data = {'name': name, 'email': email}
    response = requests.post(url, json=data)
    if response.status_code == 201:
        return response.json()['id']
    else:
        print(f"Error creating blogger: {response.text}")
        return None

blogger1_id = create_blogger('John Doe', 'john@example.com')
blogger2_id = create_blogger('Jane Smith', 'jane@example.com')

# 3. Create Blogs
def create_blog(title, description, created_by_id):
    url = f'{base_url}/Blogs'
    data = {'title': title, 'description': description, 'created_by': {'type': 'REF', 'entity': 'Bloggers', 'id': created_by_id}}
    response = requests.post(url, json=data)
    if response.status_code == 201:
        return response.json()['id']
    else:
        print(f"Error creating blog: {response.text}")
        return None

blog1_id = create_blog('Tech Blog', 'Latest technology news and reviews.', blogger1_id)
blog2_id = create_blog('Travel Blog', 'Adventures around the world', blogger2_id)

# 4. Create Tags
def create_tag(name):
    url = f'{base_url}/Tags'
    data = {'name': name}
    response = requests.post(url, json=data)
    if response.status_code == 201:
        return response.json()['id']
    else:
        print(f"Error creating tag: {response.text}")
        return None

tag1_id = create_tag('Programming')
tag2_id = create_tag('Artificial Intelligence')
tag3_id = create_tag('Travel')

# 5. Create Posts
def create_post(title, content, published_in_id, tagged_with_ids):
    url = f'{base_url}/Posts'
    data = {'title': title, 'content': content, 'published_in': {'type': 'REF', 'entity': 'Blogs', 'id': published_in_id}, 'tagged_with': [{'type': 'REF', 'entity': 'Tags', 'id': tag_id} for tag_id in tagged_with_ids]}
    response = requests.post(url, json=data)
    if response.status_code == 201:
        return response.json()['id']
    else:
        print(f"Error creating post: {response.text}")
        return None

post1_id = create_post('Top 5 Programming Languages in 2023', 'A detailed analysis...', blog1_id, [tag1_id, tag2_id])
post2_id = create_post('Best Places to Visit in Europe', 'A travel guide to amazing destinations...', blog2_id, [tag3_id])

# 6. Create Comments
def create_comment(content, author, commented_on_id):
    url = f'{base_url}/Comments'
    data = {'content': content, 'author': author, 'commented_on': {'type': 'REF', 'entity': 'Posts', 'id': commented_on_id}}
    response = requests.post(url, json=data)
    if response.status_code == 201:
        return response.json()['id']
    else:
        print(f"Error creating comment: {response.text}")
        return None

comment1_id = create_comment('Great article! I agree with your points.', 'Jane Smith', post1_id)
comment2_id = create_comment('Beautiful photos!', 'John Doe', post2_id)

# 7. You're done! Now you have a blogging graph!

# 8. Perform Graph Queries
def execute_graph_query(query):
    url = f'{base_url}/graph/query'
    data = {'query': query}
    response = requests.post(url, json=data)
    if response.status_code == 202:
        query_id = response.json()['query_id']
        return get_graph_query_result(query_id)
    elif response.status_code == 200:
        return response.json()
    else:
        print(f"Error executing query: {response.text}")
        return None

def get_graph_query_result(query_id):
    url = f'{base_url}/graph/query/{query_id}/result'
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()['result']
    else:
        print(f"Error retrieving query result: {response.text}")
        return None

# Example Queries
print("-" * 30)
print("Find all posts published by blogger with ID 1:")
query1 = f"MATCH (b:Blogger) WHERE b.id = {blogger1_id} MATCH (p:Post)-[:PUBLISHED_IN]->(bl:Blog)-[:CREATED_BY]->(b) RETURN p"
result1 = execute_graph_query(query1)
print(result1)

print("-" * 30)
print("Find all posts tagged with 'Programming':")
query2 = f"MATCH (t:Tag) WHERE t.name = 'Programming' MATCH (p:Post)-[:TAGGED_WITH]->(t) RETURN p"
result2 = execute_graph_query(query2)
print(result2)

print("-" * 30)
print("Find all comments made on post with ID 1:")
query3 = f"MATCH (p:Post) WHERE p.id = {post1_id} MATCH (c:Comment)-[:COMMENTED_ON]->(p) RETURN c"
result3 = execute_graph_query(query3)
print(result3)

print("-" * 30)
print("Find all bloggers who have commented on post with ID 1:")
query4 = f"MATCH (p:Post) WHERE p.id = {post1_id} MATCH (c:Comment)-[:COMMENTED_ON]->(p) RETURN DISTINCT c.author"
result4 = execute_graph_query(query4)
print(result4)

print("-" * 30)
print("Find all posts tagged with 'Programming' that have been commented on by blogger with ID 1:")
query5 = f"MATCH (b:Blogger) WHERE b.id = {blogger1_id} MATCH (p:Post)-[:TAGGED_WITH]->(t:Tag) WHERE t.name = 'Programming' MATCH (c:Comment)-[:COMMENTED_ON]->(p) WHERE c.author = b.name RETURN p"
result5 = execute_graph_query(query5)
print(result5)

print("-" * 30)
print("Find all posts that have been commented on by bloggers who have also created blogs tagged with 'Programming':")
query6 = f"MATCH (b:Blogger)-[:CREATED_BY]->(bl:Blog)-[:PUBLISHED_IN]->(p1:Post)-[:TAGGED_WITH]->(t1:Tag) WHERE t1.name = 'Programming' MATCH (b)-[:CREATED_BY]->(bl)-[:PUBLISHED_IN]->(p2:Post)-[:COMMENTED_ON]->(c:Comment) RETURN p2"
result6 = execute_graph_query(query6)
print(result6)

```

**Remember:**

* Consult the official rserv 0.3.9 documentation for the latest information on Sulpher support. 
* Keep in mind that the Sulpher implementation in rserv is evolving, and more advanced features may be added in future releases. 

---


