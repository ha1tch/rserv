
## Part 1: Introduction and Installation

### 1.1 Introduction

rserv is a simple, flexible, and lightweight REST prototyping server designed for rapid development and data exploration.  It provides an easy-to-use interface for managing data using a document-oriented approach, enabling you to build REST APIs and experiment with data structures quickly.

rserv is built around the concept of **entities** and **documents**. An entity represents a category or type of data, similar to a table in a relational database.  Each document is an individual data record within an entity and is stored as a separate JSON file.  rserv offers two modes of operation:

* **Schema-less Mode:** This allows for rapid prototyping and evolving data structures without predefining a strict schema.
* **Schema-enforced Mode:**  You can define a schema for each entity to enforce data consistency and structure.

rserv 0.3.9 introduces significant new features, focusing on **graph database capabilities:**

* **Sulpher Query Language:** A powerful and intuitive query language for graph traversal and analysis.
* **Indexed Graph:**  Optional support for indexed graph data structures, enabling efficient graph traversal and query performance.
* **Asynchronous Query Execution:** Queries are executed asynchronously, reducing blocking operations and improving performance.

rserv is ideal for:

* **Rapid Prototyping:**  Quickly build REST APIs for your applications and explore data models.
* **Data Exploration:**  Experiment with data structures and relationships without the overhead of setting up a full-fledged database.
* **Small-scale Applications:**  Use rserv for data storage and retrieval in small-scale projects.

### 1.2 Installation

#### Prerequisites

* **Python 3.7 or later:** rserv is written in Python and requires Python 3.7 or later to run.
* **`rserv.py` File:** Download the `rserv.py` file from the official rserv repository ([https://github.com/your-repo-link-here](https://github.com/your-repo-link-here)).

#### Running rserv

1. **Navigate to the directory containing `rserv.py`:** Use your terminal or command prompt to navigate to the directory where you downloaded `rserv.py`.
2. **Run the script:**  Execute the following command:

   ```bash
   python rserv.py 
   ```

   This will start the rserv server on the default host (0.0.0.0) and port (9090). You can customize the host and port using the command-line arguments `--host` and `--port`:

   ```bash
   python rserv.py --host 127.0.0.1 --port 8080
   ```

rserv will now be running, and you can start making API requests to it. 

**Next Steps:**

* **Part 2: Basic Data Management (CRUD Operations)**:  Learn how to create, read, update, and delete data in rserv.
* **Part 3: Graph Operations and Query Language:** Explore rserv's graph capabilities and the Sulpher query language. 

**Important Note:**  Since rserv is a single Python file, it will be executed within the current directory. You may need to ensure you have write permissions in the directory to allow rserv to create and store data files. 

---

