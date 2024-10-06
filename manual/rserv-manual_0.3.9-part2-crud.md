## Part 2: Basic Data Management (CRUD Operations)

### 2.1 Entities and Documents

rserv's data model is based on **entities** and **documents**. An entity represents a category or type of data. Think of it like a table in a relational database.  A document is an individual data record within an entity, stored as a separate JSON file. 

For example, you might have an entity called "users" to store information about your application's users. Each user would be represented by a separate document within the "users" entity.

### 2.2 CRUD Operations

rserv supports the four basic CRUD (Create, Read, Update, Delete) operations for managing documents:

#### 2.2.1 Creating Documents

**Method:** POST

**Endpoint:** `/api/v1/<entity>`

**Body:** A JSON object representing the data for the new document.

**Response:**

* **201 Created:** If the document is successfully created. The response body will include the ID of the new document.
* **400 Bad Request:**  If the request is malformed or missing required information.

**Example:**

To create a new user document with the name "John Doe" and email "john@example.com":

```bash
curl -X POST http://localhost:9090/api/v1/users -H "Content-Type: application/json" -d '{"name": "John Doe", "email": "john@example.com"}'
```

**Python:**

```python
import requests
requests.post('http://localhost:9090/api/v1/users', json={"name": "John Doe", "email": "john@example.com"})
```

#### 2.2.2 Retrieving Documents

**Method:** GET

**Endpoint:** `/api/v1/<entity>/<id>`

**Response:**

* **200 OK:** If the document is found. The response body will contain the JSON data of the document.
* **404 Not Found:** If the document with the specified ID is not found.

**Example:**

To retrieve the user document with ID 1:

```bash
curl http://localhost:9090/api/v1/users/1
```

**Python:**

```python
import requests
requests.get('http://localhost:9090/api/v1/users/1').json()
```

#### 2.2.3 Updating Documents

**Method:** PUT

**Endpoint:** `/api/v1/<entity>/<id>`

**Body:** A JSON object containing the updated data for the document.

**Response:**

* **200 OK:** If the document is successfully updated.
* **404 Not Found:** If the document with the specified ID is not found.
* **400 Bad Request:**  If the request is malformed or missing required information.

**Example:**

To update the user document with ID 1, changing the name to "John Smith" and email to "john.smith@example.com":

```bash
curl -X PUT http://localhost:9090/api/v1/users/1 -H "Content-Type: application/json" -d '{"name": "John Smith", "email": "john.smith@example.com"}'
```

**Python:**

```python
import requests
requests.put('http://localhost:9090/api/v1/users/1', json={"name": "John Smith", "email": "john.smith@example.com"})
```

#### 2.2.4 Patching Documents

**Method:** PATCH

**Endpoint:** `/api/v1/<entity>/<id>`

**Body:** A JSON object containing only the fields to be updated.

**Response:**

* **200 OK:** If the document is successfully patched.
* **404 Not Found:** If the document with the specified ID is not found.
* **400 Bad Request:**  If the request is malformed or missing required information.

**Example:**

To update only the email address of the user document with ID 1:

```bash
curl -X PATCH http://localhost:9090/api/v1/users/1 -H "Content-Type: application/json" -d '{"email": "new.john@example.com"}'
```

**Python:**

```python
import requests
requests.patch('http://localhost:9090/api/v1/users/1', json={"email": "new.john@example.com"})
```

**Null Value Handling:**

rserv provides configurable behavior for handling null values in PATCH requests:

* **Store Null Values (Default):** When a property is set to null in a PATCH request, rserv will store this null value, effectively setting the property to null in the document.
* **Delete Null Properties:** In this mode, if a property is set to null in a PATCH request, rserv will remove the property from the document entirely.

You can configure this behavior using the `patch_null` setting in your rserv configuration.

#### 2.2.5 Deleting Documents

**Method:** DELETE

**Endpoint:** `/api/v1/<entity>/<id>`

**Response:**

* **200 OK:** If the document is successfully deleted.
* **404 Not Found:** If the document with the specified ID is not found.

**Example:**

To delete the user document with ID 1:

```bash
curl -X DELETE http://localhost:9090/api/v1/users/1
```

**Python:**

```python
import requests
requests.delete('http://localhost:9090/api/v1/users/1')
```

### 2.3 ID Management

#### 2.3.1 Auto-Incrementing IDs

When using the `POST /api/v1/<entity>` endpoint to create a new document, rserv will automatically generate a unique ID for the document. This ID is an integer that is automatically incremented for each new document created within the entity. 

#### 2.3.2 Custom IDs

If you need to control the IDs of your documents, you can use the `POST /api/v1/<entity>/save/<id>` endpoint. This endpoint allows you to specify the ID for the new document.  

**Example:**

To create a new user document with ID 100:

```bash
curl -X POST http://localhost:9090/api/v1/users/save/100 -H "Content-Type: application/json" -d '{"name": "Jane Doe", "email": "jane@example.com"}'
```

**Python:**

```python
import requests
requests.post('http://localhost:9090/api/v1/users/save/100', json={"name": "Jane Doe", "email": "jane@example.com"})
```

If a document with the specified ID already exists, the server will return a **409 Conflict** status.

### 2.4 Schema-less Mode

In schema-less mode, rserv doesn't enforce a predefined structure for your documents. This allows you to be flexible and adapt your data models as your application evolves. However, it's important to implement validation on the client-side to ensure data consistency. 

### 2.5 Schema Enforcement

You can define a schema for each entity to enforce data consistency and structure. A schema is a JSON file that defines the allowed fields, data types, and other constraints for documents within that entity.  

**Schema Example:**

```json
{
  "name": {
    "type": "string",
    "required": true,
    "max_length": 255
  },
  "email": {
    "type": "string",
    "required": true,
    "regex": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
  },
  "age": {
    "type": "integer",
    "required": false,
    "min": 0,
    "max": 150
  }
}
```

To use schemas, you need to:

1. **Create Schema Files:** Create JSON files for your schemas in the `schema` directory. The file name should match the entity name. 
2. **Configure rserv:**  Set the `schema_name` configuration option to the name of the directory containing your schema files.

When using a schema, rserv will:

* **Validate Data:** Check if incoming data conforms to the schema definition.
* **Return Errors:** If data is invalid, rserv will return a **400 Bad Request** error with details about the validation errors.

**Next Steps:**

* **Part 3: Graph Operations and Query Language:** Explore rserv's graph capabilities and the Sulpher query language. 

---

