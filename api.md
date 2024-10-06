## rserv endpoint implementation 
### evolution across versions

| Method | Endpoint Signature | 0.3.1 | 0.3.2 | 0.3.3 | 0.3.4 | 0.3.5 | 0.3.6 | 0.3.7 | 0.3.8 | 0.3.9 |
|---|---|---|---|---|---|---|---|---|---|
| **POST** | `/api/v1/<entity>` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **GET** | `/api/v1/<entity>/<id>` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **PUT** | `/api/v1/<entity>/<id>` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **PATCH** | `/api/v1/<entity>/<id>` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **DELETE** | `/api/v1/<entity>/<id>` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **POST** | `/api/v1/<entity>/save/<id>` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **GET** | `/api/v1/<entity>/list` |  |  |  |  |  | ✓ | ✓ | ✓ | ✓ | 
| **POST** | `/api/v1/search` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **POST** | `/api/v1/graph/query` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **GET** | `/api/v1/graph/query/<query_id>` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **GET** | `/api/v1/graph/query/<query_id>/result` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **GET** | `/api/v1/graph/nodes/<node_id>` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 
| **POST** | `/api/v1/graph/shortestPath` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **POST** | `/api/v1/graph/nodes/search` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **POST** | `/api/v1/graph/subgraph` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **GET** | `/api/v1/graph/nodes/<node_id>/relationships` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **POST** | `/api/v1/graph/commonNeighbors` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 
| **GET** | `/api/v1/graph/nodes/<node_id>/degree` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **POST** | `/api/v1/graph/pathExists` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **POST** | `/api/v1/graph/nodes/neighborhoodAggregate` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **GET** | `/api/v1/graph/statistics` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **GET** | `/api/v1/graph/<node_ref>/in` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **GET** | `/api/v1/graph/<node_ref>/out` |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |


**Legend:**

* ✓: Fully implemented for that version
*  : Not implemented for that version

**Notes:**

* The table assumes that an endpoint is "fully implemented" when it works correctly and returns accurate data. 
* Some endpoints may have been partially implemented in earlier versions but are marked as fully implemented in later versions.
* The **graph operations** endpoints are only available if the `graph_enabled` configuration is set to `True`. 
