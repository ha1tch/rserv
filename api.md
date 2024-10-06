## rserv Endpoint Implementation Table

| Endpoint  | 0.3.1 | 0.3.2 | 0.3.3 | 0.3.4 | 0.3.5 | 0.3.6 | 0.3.7 | 0.3.8 | 0.3.9 |
|---|---|---|---|---|---|---|---|---|---|
| **CRUD Operations** |  |  |  |  |  |  |  |  |  |
|  `/api/v1/<entity>` (POST) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/<entity>/<id>` (GET) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/<entity>/<id>` (PUT) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/<entity>/<id>` (PATCH) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/<entity>/<id>` (DELETE) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/<entity>/save/<id>` (POST) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Pagination & Sorting** |  |  |  |  |  |  |  |  |  |
|  `/api/v1/<entity>/list` (GET) |  |  |  |  |  |  | ✓ | ✓ | ✓ |
| **Full-text Search** |  |  |  |  |  |  |  |  |  |
|  `/api/v1/search` (POST) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Graph Operations** |  |  |  |  |  |  |  |  |  |
|  `/api/v1/graph/query` (POST) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/graph/query/<query_id>` (GET) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/graph/query/<query_id>/result` (GET) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/graph/nodes/<node_id>` (GET) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/graph/shortestPath` (POST) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/graph/nodes/search` (POST) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/graph/subgraph` (POST) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/graph/nodes/<node_id>/relationships` (GET) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/graph/commonNeighbors` (POST) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/graph/nodes/<node_id>/degree` (GET) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/graph/pathExists` (POST) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/graph/nodes/neighborhoodAggregate` (POST) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/graph/statistics` (GET) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/graph/<node_ref>/in` (GET) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
|  `/api/v1/graph/<node_ref>/out` (GET) |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 

**Notes:**

* The table assumes that an endpoint is "fully implemented" when it works correctly and returns accurate data. 
* Some endpoints may have been partially implemented in earlier versions but are marked as fully implemented in later versions.
* The **graph operations** endpoints are only available if the `graph_enabled` configuration is set to `True`. 

This table should help you understand how the `rserv` server has evolved with each version and what functionality was added in each release. 
