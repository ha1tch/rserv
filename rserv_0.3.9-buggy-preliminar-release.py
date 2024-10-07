
import os
import json
import time
import uuid
import asyncio
import logging
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict, deque
from flask import Flask, request, jsonify, Response, abort, url_for
import re
from datetime import datetime, timedelta
import functools
import fcntl
import multiprocessing
from cachetools import TTLCache

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Constants and configurations
BASE_DIR = 'data'
SCHEMA_DIR = 'schema'
DEFAULT_SCHEMA = 'default'
RSERV_VERSION = "0.3.9"
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(SCHEMA_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    'patch_null': 'store',
    'host': '0.0.0.0',
    'port': 9090,
    'cache_ttl': 300,
    'default_page_size': 10,
    'schema_name': DEFAULT_SCHEMA,
    'cascading_delete': False,
    'rserv_graph': 'indexed',  # 'disabled', 'memory', 'indexed'
    'adjacency_list_file': 'graph.data',
    'adjacency_index_file': 'graph.index',
    'graph_query_ttl': 86400,  # 24 hours
    'graph_result_ttl': 3600,  # 1 hour
    'fulltext_enabled': False,
    'ref_embed_depth': 3,
    'max_query_depth': 10,
    'cache_type': 'ttlcache',  # 'ttlcache' or 'redis'
    'redis_host': 'localhost',  # Redis host if using Redis cache
    'redis_port': 6379  # Redis port if using Redis cache
}

config = DEFAULT_CONFIG.copy()
for key, value in os.environ.items():
    if key.lower() in config:
        if isinstance(config[key.lower()], bool):
            config[key.lower()] = value.lower() in ('true', '1', 'yes')
        elif isinstance(config[key.lower()], int):
            config[key.lower()] = int(value)
        else:
            config[key.lower()] = value

# Initialize cache
try:
    import redis
    if config['cache_type'] == 'redis':
        cache = redis.Redis(host=config['redis_host'], port=config['redis_port'])
        logger.info(f"Using Redis cache at {config['redis_host']}:{config['redis_port']}")
    else:
        cache = TTLCache(maxsize=1024, ttl=config['cache_ttl'])
        logger.info(f"Using in-memory TTLCache with TTL {config['cache_ttl']} seconds")
except ImportError:
    cache = TTLCache(maxsize=1024, ttl=config['cache_ttl'])
    logger.info("Redis module not available. Using in-memory TTLCache.")


# Global variables
graph = defaultdict(dict)
fulltext_index = defaultdict(set)
query_storage = {}
index = {}

# Error handling
class RServError(Exception):
    def __init__(self, message: str, status_code: int = 400, payload: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.payload = payload

    def to_dict(self) -> Dict[str, Any]:
        error_dict = dict(self.payload or ())
        error_dict['message'] = self.message
        return error_dict

@app.errorhandler(RServError)
def handle_rserv_error(error: RServError) -> Tuple[Response, int]:
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response

# Helper functions for HATEOAS and consistent responses
def create_error_response(message: str, status_code: int, details: Optional[Dict] = None) -> Tuple[Dict[str, Any], int]:
    response = {
        "error": {
            "message": message,
            "status_code": status_code
        },
        "_links": {
            "self": {"href": request.url}
        }
    }
    if details:
        response['error']['details'] = details
    return jsonify(response), status_code

def create_resource_response(resource_type: str, data: Any, links: Dict[str, str] = None) -> Dict[str, Any]:
    response = {
        "resource_type": resource_type,
        "data": data,
        "_links": {
            "self": {"href": request.url}
        }
    }
    if links:
        response["_links"].update(links)
    return response

def create_collection_response(resource_type: str, items: List[Any], links: Dict[str, str] = None) -> Dict[str, Any]:
    response = {
        "resource_type": f"{resource_type}_collection",
        "items": items,
        "_links": {
            "self": {"href": request.url}
        }
    }
    if links:
        response["_links"].update(links)
    return response

# Schema handling
def load_schemas(schema_name: str) -> Dict[str, Any]:
    schema_dir = os.path.join(SCHEMA_DIR, schema_name)
    schemas = {}
    if os.path.exists(schema_dir):
        for filename in os.listdir(schema_dir):
            if filename.endswith('.json'):
                entity_name = os.path.splitext(filename)[0]
                with open(os.path.join(schema_dir, filename), 'r') as f:
                    schemas[entity_name] = json.load(f)
    return schemas

schemas = load_schemas(config['schema_name'])

# CRUD operations
def get_entity_dir(entity: str) -> str:
    entity_dir = os.path.join(BASE_DIR, config['schema_name'], entity)
    os.makedirs(entity_dir, exist_ok=True)
    return entity_dir

def get_entity_file(entity: str, id: int) -> str:
    return os.path.join(get_entity_dir(entity), f"{id}.json")

def get_next_id(entity: str) -> int:
    entity_dir = get_entity_dir(entity)
    id_file = os.path.join(entity_dir, f"{entity}_next_id.json")

    try:
        if os.path.exists(id_file):
            with open(id_file, 'r') as f:
                next_id = json.load(f) + 1
        else:
            next_id = 1
        with open(id_file, 'w') as f:
            json.dump(next_id, f)
        return next_id
    except Exception as e:
        logger.error(f"Error updating next ID for entity {entity}: {str(e)}")
        raise RServError(f"Error generating ID for entity {entity}", status_code=500)

@app.route('/api/v1/<entity>', methods=['POST'])
def create_entity(entity: str) -> Tuple[Response, int]:
    try:
        validate_entity_name(entity)
        data = request.json
        if not data:
            raise RServError("No input data provided", status_code=400)
        
        new_id = get_next_id(entity)
        data['id'] = new_id
        file_path = get_entity_file(entity, new_id)
        
        with open(file_path, 'w') as f:
            json.dump(data, f)
        
        if config['fulltext_enabled']:
            index_document(entity, new_id, data)
        
        if config['rserv_graph'] == 'indexed':
            update_graph_index(entity, new_id, data, 'create')
            update_graph(entity, new_id, data)
            save_graph_index(config['adjacency_index_file'])
            save_graph_to_file(config['adjacency_list_file'])
        
        # Invalidate cache for this entity after creation
        invalidate_cache(entity)
        
        logger.info(f"Created resource of entity {entity} with id {new_id}")
        return jsonify({"message": f"New resource of entity {entity} created successfully with id {new_id}", "id": new_id}), 201
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in create_entity: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)

@app.route('/api/v1/<entity>/<int:id>', methods=['GET'])
def get_entity(entity: str, id: int) -> Tuple[Response, int]:
    try:
        validate_entity_name(entity)
        validate_id(id)
        
        # Check if entity is in cache
        cache_key = f"{entity}:{id}"
        if cache_key in cache:
            logger.info(f"Retrieved resource of entity {entity} with id {id} from cache")
            return jsonify(cache[cache_key]), 200
        
        file_path = get_entity_file(entity, id)
        if not os.path.exists(file_path):
            raise RServError(f"Resource of entity {entity} with id {id} not found", status_code=404)
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        lookup = request.args.get('lookup')
        if lookup:
            embed_depth = request.args.get('embed_depth', config['ref_embed_depth'], type=int)
            data = populate_document(entity, data, lookup.split(','), max_depth=embed_depth)
        
        # Cache the retrieved entity
        cache[cache_key] = data
        
        logger.info(f"Retrieved resource of entity {entity} with id {id}")
        return jsonify(data), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in get_entity: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)

@app.route('/api/v1/<entity>/<int:id>', methods=['PUT'])
def update_entity(entity: str, id: int) -> Tuple[Response, int]:
    try:
        validate_entity_name(entity)
        validate_id(id)
        
        file_path = get_entity_file(entity, id)
        if not os.path.exists(file_path):
            raise RServError(f"Resource of entity {entity} with id {id} not found", status_code=404)
        
        data = request.json
        if not data:
            raise RServError("No input data provided", status_code=400)
        
        data['id'] = id
        
        # Validate foreign keys before updating
        is_valid, errors = validator.validate(entity, data)
        if not is_valid:
            return jsonify({"error": "Validation failed", "details": errors}), 400

        with open(file_path, 'w') as f:
            json.dump(data, f)
        
        if config['fulltext_enabled']:
            index_document(entity, id, data)
        
        if config['rserv_graph'] == 'indexed':
            update_graph_index(entity, id, data, 'update')
            update_graph(entity, id, data)
            save_graph_index(config['adjacency_index_file'])
            save_graph_to_file(config['adjacency_list_file'])
        
        # Invalidate cache for this entity after update
        invalidate_cache(entity)
        
        logger.info(f"Updated resource of entity {entity} with id {id}")
        return jsonify({"message": f"Resource of entity {entity} with id {id} updated successfully"}), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in update_entity: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)

@app.route('/api/v1/<entity>/<int:id>', methods=['PATCH'])
def patch_entity(entity: str, id: int) -> Tuple[Response, int]:
    try:
        validate_entity_name(entity)
        validate_id(id)
        
        file_path = get_entity_file(entity, id)
        if not os.path.exists(file_path):
            raise RServError(f"Resource of entity {entity} with id {id} not found", status_code=404)
        
        with open(file_path, 'r') as f:
            existing_data = json.load(f)
        
        patch_data = request.json
        if not patch_data:
            raise RServError("No input data provided", status_code=400)
        
        # Validate foreign keys before patching
        merged_data = {**existing_data, **patch_data}
        is_valid, errors = validator.validate(entity, merged_data)
        if not is_valid:
            return jsonify({"error": "Validation failed", "details": errors}), 400

        for key, value in patch_data.items():
            if key != 'id':
                if value is None and config['patch_null'] == 'delete':
                    existing_data.pop(key, None)
                else:
                    existing_data[key] = value
        
        with open(file_path, 'w') as f:
            json.dump(existing_data, f)
        
        if config['fulltext_enabled']:
            index_document(entity, id, existing_data)
        
        if config['rserv_graph'] == 'indexed':
            update_graph_index(entity, id, existing_data, 'update')
            update_graph(entity, id, existing_data)
            save_graph_index(config['adjacency_index_file'])
            save_graph_to_file(config['adjacency_list_file'])
        
        # Invalidate cache for this entity after patch
        invalidate_cache(entity)
        
        logger.info(f"Patched {entity} with id {id}")
        return jsonify({
            "message": f"{entity} with id {id} patched successfully",
            "updated_fields": list(patch_data.keys())
        }), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in patch_entity: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)

@app.route('/api/v1/<entity>/<int:id>', methods=['DELETE'])
def delete_entity(entity: str, id: int) -> Tuple[Response, int]:
    try:
        validate_entity_name(entity)
        validate_id(id)
        
        file_path = get_entity_file(entity, id)
        if not os.path.exists(file_path):
            raise RServError(f"Resource of entity {entity} with id {id} not found", status_code=404)
        
        if config['cascading_delete']:
            deleted = cascade_delete(entity, id)
        else:
            os.remove(file_path)
            deleted = [f"{entity}:{id}"]
        
        if config['fulltext_enabled']:
            for item in deleted:
                e, i = item.split(':')
                remove_from_index(e, int(i))
        
        if config['rserv_graph'] == 'indexed':
            for item in deleted:
                e, i = item.split(':')
                data = get_entity_data(e, int(i))
                update_graph_index(e, int(i), data, 'delete')
                remove_from_graph(e, int(i))
            save_graph_index(config['adjacency_index_file'])
            save_graph_to_file(config['adjacency_list_file'])
        
        # Invalidate cache for this entity after deletion
        invalidate_cache(entity)
        
        logger.info(f"Deleted {entity} with id {id}")
        return jsonify({"message": f"{entity} with id {id} deleted successfully", "cascaded_deletes": deleted}), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in delete_entity: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)

def cascade_delete(entity: str, id: int) -> List[str]:
    deleted = []
    to_delete = [(entity, id)]
    
    while to_delete:
        current_entity, current_id = to_delete.pop(0)
        file_path = get_entity_file(current_entity, current_id)
        
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            os.remove(file_path)
            deleted.append(f"{current_entity}:{current_id}")
            
            # Find references to this entity in other entities
            for e in os.listdir(os.path.join(BASE_DIR, config['schema_name'])):
                entity_dir = get_entity_dir(e)
                for filename in os.listdir(entity_dir):
                    if filename.endswith('.json'):
                        with open(os.path.join(entity_dir, filename), 'r') as f:
                            other_data = json.load(f)
                        
                        for key, value in other_data.items():
                            if isinstance(value, dict) and value.get('type') == 'REF':
                                if value.get('entity') == current_entity and value.get('id') == current_id:
                                    to_delete.append((e, other_data['id']))
    
    return deleted

@app.route('/api/v1/<entity>/save/<int:id>', methods=['POST'])
def save_entity(entity: str, id: int) -> Tuple[Response, int]:
    try:
        validate_entity_name(entity)
        validate_id(id)
        
        file_path = get_entity_file(entity, id)
        if os.path.exists(file_path):
            raise RServError(f"Resource of entity {entity} with id {id} already exists", status_code=409)
        
        data = request.json
        if not data:
            raise RServError("No input data provided", status_code=400)
        
        data['id'] = id
        
        # Validate foreign keys before saving
        is_valid, errors = validator.validate(entity, data)
        if not is_valid:
            return jsonify({"error": "Validation failed", "details": errors}), 400

        with open(file_path, 'w') as f:
            json.dump(data, f)
        
        if config['fulltext_enabled']:
            index_document(entity, id, data)
        
        if config['rserv_graph'] == 'indexed':
            update_graph_index(entity, id, data, 'create')
            update_graph(entity, id, data)
            save_graph_index(config['adjacency_index_file'])
            save_graph_to_file(config['adjacency_list_file'])
        
        # Invalidate cache for this entity after saving
        invalidate_cache(entity)
        
        logger.info(f"Saved resource of entity {entity} with id {id}")
        return jsonify({"message": f"Resource of entity {entity} saved successfully with id {id}"}), 201
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in save_entity: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)

# Pagination and sorting
def get_pagination_params() -> Tuple[int, int]:
    page = max(1, request.args.get('page', 1, type=int))
    per_page = max(1, min(100, request.args.get('per_page', config['default_page_size'], type=int)))
    return page, per_page

def get_sorting_params() -> List[Tuple[str, str]]:
    sort_params = request.args.get('sort', 'id:asc')
    return [tuple(param.split(':')) for param in sort_params.split(',')]

def sort_entities(entities: List[Dict[str, Any]], sort_params: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    def multi_field_comparator(a: Dict[str, Any], b: Dict[str, Any]) -> int:
        for field, order in sort_params:
            a_val = a.get(field)
            b_val = b.get(field)
            if a_val != b_val:
                if order == 'asc':
                    return (a_val > b_val) - (a_val < b_val)
                else:
                    return (a_val < b_val) - (a_val > b_val)
        return 0
    
    return sorted(entities, key=functools.cmp_to_key(multi_field_comparator))

def paginate_results(results: List[Dict[str, Any]], page: int, per_page: int) -> Dict[str, Any]:
    total = len(results)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "items": results[start:end],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages
    }

@app.route('/api/v1/<entity>/list', methods=['GET'])
def list_entities(entity: str) -> Tuple[Response, int]:
    try:
        validate_entity_name(entity)
        
        page, per_page = get_pagination_params()
        sort_params = get_sorting_params()
        
        # Check if paginated list is in cache
        cache_key = f"{entity}:list:{page}:{per_page}:{sort_params}"
        if cache_key in cache:
            logger.info(f"Retrieved paginated list of {entity} from cache")
            return jsonify(cache[cache_key]), 200
        
        entities = get_all_entities(entity)
        sorted_entities = sort_entities(entities, sort_params)
        paginated_results = paginate_results(sorted_entities, page, per_page)
        
        # Cache the paginated results
        cache[cache_key] = paginated_results
        
        logger.info(f"Listed {entity} (page {page}, {per_page} per page)")
        return jsonify(paginated_results), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in list_entities: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)

def get_all_entities(entity: str) -> List[Dict[str, Any]]:
    entity_dir = get_entity_dir(entity)
    entities = []
    for filename in os.listdir(entity_dir):
        if filename.endswith('.json'):
            with open(os.path.join(entity_dir, filename), 'r') as f:
                entities.append(json.load(f))
    return entities

# Full-text search
def tokenize(text: str) -> List[str]:
    return re.findall(r'\w+', text.lower())

def index_document(entity: str, doc_id: int, content: Dict[str, Any]) -> None:
    tokens = set(tokenize(json.dumps(content)))
    for token in tokens:
        fulltext_index[token].add(f"{entity}:{doc_id}")

def remove_from_index(entity: str, doc_id: int) -> None:
    for token_set in fulltext_index.values():
        token_set.discard(f"{entity}:{doc_id}")

def search_fulltext(query: str, limit: int = 10) -> List[str]:
    query_tokens = tokenize(query)
    results = defaultdict(int)
    for token in query_tokens:
        for doc_ref in fulltext_index.get(token, []):
            results[doc_ref] += 1
    
    return sorted(results, key=results.get, reverse=True)[:limit]

@app.route('/api/v1/search', methods=['POST'])
def fulltext_search() -> Tuple[Response, int]:
    try:
        if not config['fulltext_enabled']:
            raise RServError("Full-text search is not enabled", status_code=400)
        
        data = request.json
        if not data:
            raise RServError("No input data provided", status_code=400)
        
        query = data.get('query')
        if not query:
            raise RServError("Query is required", status_code=400)
        
        limit = data.get('limit', 10)
        
        results = search_fulltext(query, limit)
        
        documents = []
        for doc_ref in results:
            entity, doc_id = doc_ref.split(':')
            doc = get_entity(entity, int(doc_id))
            if doc:
                documents.append(doc)
        
        return jsonify({"results": documents}), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in fulltext_search: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)

# Graph operations
def update_graph(entity: str, id: int, data: Dict[str, Any]) -> None:
    if not config['graph_enabled']:
        return

    node_id = f"{entity}:{id}"
    
    # Remove existing edges for this node
    remove_from_graph(entity, id)
    
    # Add new edges based on current data
    for key, value in data.items():
        if isinstance(value, dict) and value.get('type') == 'REF':
            ref_entity = value.get('entity')
            ref_id = value.get('id')
            if ref_entity and ref_id:
                target_node = f"{ref_entity}:{ref_id}"
                graph[node_id][target_node] = key
                # Add reverse edge
                graph[target_node][node_id] = f"reverse_{key}"

def remove_from_graph(entity: str, id: int) -> None:
    if not config['graph_enabled']:
        return

    node_id = f"{entity}:{id}"
    
    # Remove all edges where this node is the target
    for source_node in list(graph.keys()):
        if node_id in graph[source_node]:
            del graph[source_node][node_id]
    
    # Remove the node itself
    if node_id in graph:
        del graph[node_id]

def populate_document(entity: str, doc: Dict[str, Any], lookup_fields: List[str], depth: int = 0, max_depth: Optional[int] = None) -> Dict[str, Any]:
    if max_depth is None:
        max_depth = config['ref_embed_depth']
    
    if depth >= max_depth:
        return doc
    
    for field in lookup_fields:
        if field in doc and isinstance(doc[field], dict) and doc[field].get('type') == 'REF':
            ref = doc[field]
            ref_entity, ref_id = ref['entity'], ref['id']
            ref_doc = get_entity(ref_entity, ref_id)
            if ref_doc:
                # Replace the REF with the actual document
                doc[field] = populate_document(ref_entity, ref_doc, lookup_fields, depth + 1, max_depth)
    
    return doc


class SulpherQuery:
    def __init__(self, query_string: str, max_depth: int = config['max_query_depth']):
        self.query_string = query_string
        self.query_id = str(uuid.uuid4())
        self.status = 'pending'
        self.result = None
        self.stats = {'nodes_traversed': 0, 'start_time': None, 'end_time': None}
        self.parsed_query = None
        self.max_depth = max_depth

    def parse(self):
        pattern = r'((?:BFS|DFS) )?MATCH ((?:\([^\)]+\)(?:-\[[^\]]+\]->)?)+)(?: WHERE (.+))? RETURN (.+)'
        match = re.match(pattern, self.query_string)
        if not match:
            raise ValueError("Invalid Sulpher query format")
        
        algorithm, path_pattern, where_clause, return_clause = match.groups()
        
        # Parse path pattern
        path_parts = re.findall(r'\(([^\)]+)\)(?:-\[([^\]]+)\]->)?', path_pattern)
        parsed_path = []
        for node, relationship in path_parts:
            node_parts = node.split(':')
            node_var = node_parts[0]
            node_type = node_parts[1] if len(node_parts) > 1 else None
            node_props = self._parse_properties(node)
            
            rel_parts = relationship.split(':') if relationship else [None, None]
            rel_type = rel_parts[1] if len(rel_parts) > 1 else rel_parts[0]
            rel_props = self._parse_properties(relationship) if relationship else {}
            
            parsed_path.append({
                'node': {'var': node_var, 'type': node_type, 'props': node_props},
                'relationship': {'type': rel_type, 'props': rel_props}
            })
        
        # Parse WHERE clause
        where_conditions = self._parse_where_clause(where_clause) if where_clause else None
        
        # Parse RETURN clause
        return_items = [item.strip() for item in return_clause.split(',')]
        
        self.parsed_query = {
            'algorithm': algorithm.strip() if algorithm else 'BFS',
            'path': parsed_path,
            'where': where_conditions,
            'return': return_items
        }

    def _parse_properties(self, string: str) -> Dict[str, Any]:
        props_match = re.search(r'{([^}]+)}', string)
        if not props_match:
            return {}
        props_str = props_match.group(1)
        return {k.strip(): self._parse_value(v.strip()) for k, v in [prop.split(':') for prop in props_str.split(',')]}

    def _parse_where_clause(self, where_clause: str) -> List[Dict[str, Any]]:
        conditions = where_clause.split('AND')
        parsed_conditions = []
        for condition in conditions:
            match = re.match(r'(\w+)\.(\w+)\s*([=<>]+)\s*(.+)', condition.strip())
            if match:
                var, prop, op, value = match.groups()
                parsed_conditions.append({
                    'variable': var,
                    'property': prop,
                    'operator': op,
                    'value': self._parse_value(value)
                })
        return parsed_conditions

    def _parse_value(self, value: str) -> Any:
        try:
            if value.isdigit():
                return int(value)
            elif value.replace('.', '').isdigit():
                return float(value)
            elif value.lower() in ('true', 'false'):
                return value.lower() == 'true'
            else:
                return value.strip('"\'')  # Return string if it doesn't match any type
        except ValueError:
            raise ValueError(f"Invalid value type: {value}")

    def execute(self, graph: Dict[str, Dict[str, Any]]):
        self.stats['start_time'] = time.time()
        self.parse()
        
        results = self._traverse_graph(graph)
        
        # Apply WHERE conditions
        if self.parsed_query['where']:
            results = self._apply_where_conditions(results, graph)
        
        # Process RETURN clause
        final_results = self._process_return_clause(results, graph)
        
        self.result = final_results
        self.status = 'completed'
        self.stats['end_time'] = time.time()

        # Cache the query result if it is successful
        if self.status == 'completed':
            cache_key = f"query:{self.query_id}"
            cache[cache_key] = (self.result, self.stats)

    def _traverse_graph(self, graph: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        path = self.parsed_query['path']
        start_nodes = self._find_matching_nodes(graph, path[0]['node'])
        
        results = []
        for start_node in start_nodes:
            if self.parsed_query['algorithm'] == 'BFS':
                self._bfs(graph, start_node, path, results)
            else:
                self._dfs(graph, start_node, path, 1, {path[0]['node']['var']: start_node}, results, set())
        
        return results

            

    def _bfs(self, graph: Dict[str, Dict[str, Any]], start_node: str, path: List[Dict[str, Any]], results: List[Dict[str, Any]]):
        queue = [(start_node, 1, {path[0]['node']['var']: start_node})]
        while queue:
            current_node, depth, path_so_far = queue.pop(0)
            
            if depth == len(path):
                results.append(path_so_far.copy())
                continue
            
            if depth > self.max_depth:
                continue
            
            self.stats['nodes_traversed'] += 1
            current_pattern = path[depth]
            
            for neighbor, edge_data in graph[current_node].items():
                if self._match_pattern(graph, neighbor, edge_data, current_pattern):
                    new_path = path_so_far.copy()
                    new_path[current_pattern['node']['var']] = neighbor
                    queue.append((neighbor, depth + 1, new_path))

    def _dfs(self, graph: Dict[str, Dict[str, Any]], current_node: str, path: List[Dict[str, Any]], 
             depth: int, path_so_far: Dict[str, str], results: List[Dict[str, Any]], visited: set):
        if depth == len(path):
            results.append(path_so_far.copy())
            return
        
        if depth > self.max_depth:
            return
        
        self.stats['nodes_traversed'] += 1
        current_pattern = path[depth]

        # Cycle Detection Implementation
        if config['graph_cycle_detection'] == 'error' and current_node in visited:
            raise ValueError(f"Cycle detected at node: {current_node} during DFS traversal.")
        elif config['graph_cycle_detection'] == 'disable':
            # Do nothing (cycles are ignored)
            pass
        elif config['graph_cycle_detection'] == 'warn':
            logger.warning(f"Cycle detected at node: {current_node} during DFS traversal.")
        elif config['graph_cycle_detection'] == 'ignore':
            # Do nothing (cycles are ignored)
            pass 
        else:
            raise ValueError(f"Invalid graph_cycle_detection setting: {config['graph_cycle_detection']}")

        for neighbor, edge_data in graph[current_node].items():
            if neighbor in visited:
                continue  # Skip already visited nodes to prevent cycles
            
            if self._match_pattern(graph, neighbor, edge_data, current_pattern):
                path_so_far[current_pattern['node']['var']] = neighbor
                visited.add(neighbor)
                self._dfs(graph, neighbor, path, depth + 1, path_so_far, results, visited)
                visited.remove(neighbor)
                path_so_far.pop(current_pattern['node']['var'])

    def _match_pattern(self, graph: Dict[str, Dict[str, Any]], node: str, edge_data: Dict[str, Any], pattern: Dict[str, Any]) -> bool:
        node_data = graph[node]
        return (pattern['node']['type'] is None or node_data['type'] == pattern['node']['type']) and \
               all(node_data.get(k) == v for k, v in pattern['node']['props'].items()) and \
               (pattern['relationship']['type'] is None or edge_data['type'] == pattern['relationship']['type']) and \
               all(edge_data.get(k) == v for k, v in pattern['relationship']['props'].items())

    def _find_matching_nodes(self, graph: Dict[str, Dict[str, Any]], node_pattern: Dict[str, Any]) -> List[str]:
        matching_nodes = []
        if config['rserv_graph'] == 'indexed':
            # Index-based lookup
            matching_nodes = set(index.get(node_pattern['type'], set()))
            for prop, value in node_pattern['props'].items():
                matching_nodes &= set(index.get(f"{prop}:{value}", set()))
        else:
            # Default behavior: Iterate through all nodes
            for node, data in graph.items():
                if (node_pattern['type'] is None or data['type'] == node_pattern['type']) and \
                   all(data.get(k) == v for k, v in node_pattern['props'].items()):
                    matching_nodes.append(node)
        return list(matching_nodes)  # Return a list of matching node IDs

    def _apply_where_conditions(self, results: List[Dict[str, Any]], graph: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        filtered_results = []
        for result in results:
            if all(self._evaluate_condition(condition, result, graph) for condition in self.parsed_query['where']):
                filtered_results.append(result)
        return filtered_results

    def _evaluate_condition(self, condition: Dict[str, Any], result: Dict[str, str], graph: Dict[str, Dict[str, Any]]) -> bool:
        node_id = result[condition['variable']]
        node_data = graph[node_id]
        actual_value = node_data.get(condition['property'])
        expected_value = condition['value']
        
        if condition['operator'] == '=':
            return actual_value == expected_value
        elif condition['operator'] == '>':
            return actual_value > expected_value
        elif condition['operator'] == '<':
            return actual_value < expected_value
        elif condition['operator'] == '>=':
            return actual_value >= expected_value
        elif condition['operator'] == '<=':
            return actual_value <= expected_value
        elif condition['operator'] == '!=':
            return actual_value != expected_value
        
        return False

    def _process_return_clause(self, results: List[Dict[str, Any]], graph: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        processed_results = []
        for result in results:
            processed_result = {}
            for item in self.parsed_query['return']:
                if '.' in item:
                    var, prop = item.split('.')
                    node_id = result[var]
                    node_data = graph[node_id]
                    processed_result[item] = node_data.get(prop)
                elif item.startswith(('COUNT(', 'SUM(', 'AVG(', 'MIN(', 'MAX(')):
                    var = item[item.index('(')+1:-1]  # Extract variable name from aggregation function
                    if item.startswith('COUNT('):
                        processed_result[item] = len([r.get(var) for r in results if r.get(var) is not None])
                    elif item.startswith('SUM('):
                        processed_result[item] = sum([r.get(var) for r in results if r.get(var) is not None])
                    elif item.startswith('AVG('):
                        values = [r.get(var) for r in results if r.get(var) is not None]
                        processed_result[item] = sum(values) / len(values) if len(values) > 0 else None
                    elif item.startswith('MIN('):
                        processed_result[item] = min([r.get(var) for r in results if r.get(var) is not None])
                    elif item.startswith('MAX('):
                        processed_result[item] = max([r.get(var) for r in results if r.get(var) is not None])
                else:
                    processed_result[item] = result[item]
            processed_results.append(processed_result)

        return processed_results

# API Endpoints

@app.route('/api/v1/graph/query', methods=['POST'])
def create_graph_query() -> Tuple[Response, int]:
    try:
        if not config['graph_enabled']:
            return create_error_response("Graph querying is not enabled", 400)
        
        query_string = request.json.get('query')
        max_depth = request.json.get('max_depth', config['max_query_depth'])
        
        if not query_string:
            return create_error_response("Query string is required", 400)
        
        query = SulpherQuery(query_string, max_depth)
        query_storage[query.query_id] = query
        
        # Execute query asynchronously
        asyncio.create_task(execute_graph_query(query))
        
        # Check if the query result is in cache
        cache_key = f"query:{query.query_id}"
        if cache_key in cache:
            query.status = 'completed'
            query.result, query.stats = cache[cache_key]
            response = create_resource_response("query", {
                "query_id": query.query_id,
                "status": query.status
            }, {
                "result": {"href": url_for('get_graph_query_result', query_id=query.query_id)}
            })
            return jsonify(response), 200
        
        response = create_resource_response("query", {
            "query_id": query.query_id,
            "status": query.status
        }, {
            "result": {"href": url_for('get_graph_query_result', query_id=query.query_id)}
        })
        return jsonify(response), 202
    except Exception as e:
        logger.error(f"Unexpected error in create_graph_query: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)

async def execute_graph_query(query: SulpherQuery) -> None:
    try:
        query.execute(graph)  # Assuming 'graph' is your graph data structure
    except Exception as e:
        query.status = 'failed'
        query.result = str(e)

@app.route('/api/v1/graph/query/<query_id>', methods=['GET'])
def get_graph_query_status(query_id: str) -> Tuple[Response, int]:
    try:
        if query_id not in query_storage:
            return create_error_response("Query not found", 404)
        
        query = query_storage[query_id]
        response = create_resource_response("query_status", {
            "query_id": query.query_id,
            "status": query.status
        }, {
            "result": {"href": url_for('get_graph_query_result', query_id=query.query_id)}
        })
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Unexpected error in get_graph_query_status: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)

@app.route('/api/v1/graph/query/<query_id>/result', methods=['GET'])
def get_graph_query_result(query_id: str) -> Tuple[Response, int]:
    try:
        if query_id not in query_storage:
            return create_error_response("Query not found", 404)
        
        query = query_storage[query_id]
        if query.status != 'completed':
            return create_error_response("Query has not completed yet", 400)
        
        response = create_resource_response("query_result", {
            "result": query.result,
            "stats": query.stats
        }, {
            "query": {"href": url_for('get_graph_query_status', query_id=query.query_id)}
        })
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Unexpected error in get_graph_query_result: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)

@app.route('/api/v1/graph/nodes/<node_id>', methods=['GET'])
def get_node_properties(node_id: str) -> Tuple[Response, int]:
    try:
        query = f"MATCH (n) WHERE id(n) = '{node_id}' RETURN n"
        result = execute_sulpher_query(query)
        if result:
            node_data = result[0]['n']
            links = {
                "relationships": {"href": url_for('get_relationship_types', node_id=node_id)},
                "subgraph": {"href": url_for('get_subgraph')},
                "neighborhood": {"href": url_for('get_neighborhood_aggregate')}
            }
            response = create_resource_response("node", node_data, links)
            return jsonify(response), 200
        return create_error_response("Node not found", 404)
    except Exception as e:
        logger.error(f"Unexpected error in get_node_properties: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)

@app.route('/api/v1/graph/shortestPath', methods=['POST'])
def find_shortest_path() -> Tuple[Response, int]:
    try:
        data = request.json
        start_node_id = data.get('start_node_id')
        end_node_id = data.get('end_node_id')
        max_depth = data.get('max_depth', config['max_query_depth'])

        if not start_node_id or not end_node_id:
            return create_error_response("Start and end node IDs are required", 400)

        query = f"""
        MATCH p = shortestPath((a)-[*1..{max_depth}]-(b))
        WHERE id(a) = '{start_node_id}' AND id(b) = '{end_node_id}'
        RETURN p
        """
        result = execute_sulpher_query(query)
        if result:
            path_data = result[0]['p']
            links = {
                "start_node": {"href": url_for('get_node_properties', node_id=start_node_id)},
                "end_node": {"href": url_for('get_node_properties', node_id=end_node_id)}
            }
            response = create_resource_response("shortest_path", path_data, links)
            return jsonify(response), 200
        return create_error_response("No path found", 404)
    except Exception as e:
        logger.error(f"Unexpected error in find_shortest_path: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)

@app.route('/api/v1/graph/nodes/search', methods=['POST'])
def search_nodes() -> Tuple[Response, int]:
    try:
        search_criteria = request.json
        conditions = []
        for key, value in search_criteria.items():
            conditions.append(f"n.{key} = '{value}'")
        where_clause = " AND ".join(conditions)
        query = f"MATCH (n) WHERE {where_clause} RETURN n"
        result = execute_sulpher_query(query)
        
        nodes = [node['n'] for node in result]
        links = {
            "create_node": {"href": url_for('create_node')}  # Assuming you have a create_node endpoint
        }
        response = create_collection_response("nodes", nodes, links)
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Unexpected error in search_nodes: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)


@app.route('/api/v1/graph/nodes/<node_id>/relationships', methods=['GET'])
def get_relationship_types(node_id: str) -> Tuple[Response, int]:
    try:
        direction = request.args.get('direction', default='all')
        if direction == 'in':
            query = f"MATCH (n)<-[r]-() WHERE id(n) = '{node_id}' RETURN DISTINCT type(r) as type"
        elif direction == 'out':
            query = f"MATCH (n)-[r]->() WHERE id(n) = '{node_id}' RETURN DISTINCT type(r) as type"
        else:
            query = f"MATCH (n)-[r]-() WHERE id(n) = '{node_id}' RETURN DISTINCT type(r) as type"
        
        result = execute_sulpher_query(query)
        relationship_types = [r['type'] for r in result]
        links = {
            "node": {"href": url_for('get_node_properties', node_id=node_id)},
            "incoming": {"href": url_for('get_incoming_edges', node_ref=node_id)},
            "outgoing": {"href": url_for('get_outgoing_edges', node_ref=node_id)}
        }
        response = create_collection_response("relationship_types", relationship_types, links)
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Unexpected error in get_relationship_types: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)

@app.route('/api/v1/graph/commonNeighbors', methods=['POST'])
def get_common_neighbors() -> Tuple[Response, int]:
    try:
        data = request.json
        node_id1 = data.get('node_id1')
        node_id2 = data.get('node_id2')

        if not node_id1 or not node_id2:
            return create_error_response("Both node IDs are required", 400)

        query = f"""
        MATCH (a)-[]-(c)-[]-(b)
        WHERE id(a) = '{node_id1}' AND id(b) = '{node_id2}'
        RETURN DISTINCT c
        """
        result = execute_sulpher_query(query)
        common_neighbors = [r['c'] for r in result]
        links = {
            "node1": {"href": url_for('get_node_properties', node_id=node_id1)},
            "node2": {"href": url_for('get_node_properties', node_id=node_id2)}
        }
        response = create_collection_response("common_neighbors", common_neighbors, links)
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Unexpected error in get_common_neighbors: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)

@app.route('/api/v1/graph/nodes/<node_id>/degree', methods=['GET'])
def get_node_degree(node_id: str) -> Tuple[Response, int]:
    try:
        direction = request.args.get('direction', default='all')
        if direction == 'in':
            query = f"MATCH (n)<-[r]-() WHERE id(n) = '{node_id}' RETURN count(r) as degree"
        elif direction == 'out':
            query = f"MATCH (n)-[r]->() WHERE id(n) = '{node_id}' RETURN count(r) as degree"
        else:
            query = f"MATCH (n)-[r]-() WHERE id(n) = '{node_id}' RETURN count(r) as degree"
        result = execute_sulpher_query(query)
        degree = result[0]['degree']
        links = {
            "node": {"href": url_for('get_node_properties', node_id=node_id)},
            "relationships": {"href": url_for('get_relationship_types', node_id=node_id)}
        }
        response = create_resource_response("node_degree", {"node_id": node_id, "degree": degree, "direction": direction}, links)
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Unexpected error in get_node_degree: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)

@app.route('/api/v1/graph/pathExists', methods=['POST'])
def check_path_existence() -> Tuple[Response, int]:
    try:
        data = request.json
        start_node_id = data.get('start_node_id')
        end_node_id = data.get('end_node_id')
        max_depth = data.get('max_depth', config['max_query_depth'])

        if not start_node_id or not end_node_id:
            return create_error_response("Start and end node IDs are required", 400)

        query = f"""
        MATCH p = (a)-[*1..{max_depth}]-(b)
        WHERE id(a) = '{start_node_id}' AND id(b) = '{end_node_id}'
        RETURN exists(p) as path_exists
        """
        result = execute_sulpher_query(query)
        path_exists = result[0]['path_exists']
        links = {
            "start_node": {"href": url_for('get_node_properties', node_id=start_node_id)},
            "end_node": {"href": url_for('get_node_properties', node_id=end_node_id)},
            "shortest_path": {"href": url_for('find_shortest_path')}
        }
        response = create_resource_response("path_existence", {
            "start_node_id": start_node_id,
            "end_node_id": end_node_id,
            "path_exists": path_exists,
            "max_depth": max_depth
        }, links)
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Unexpected error in check_path_existence: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)

@app.route('/api/v1/graph/nodes/neighborhoodAggregate', methods=['POST'])
def get_neighborhood_aggregate() -> Tuple[Response, int]:
    try:
        data = request.json
        node_id = data.get('node_id')
        depth = data.get('depth', 1)
        agg_property = data.get('property', 'id')
        agg_function = data.get('aggregation', 'count')
        
        if not node_id:
            return create_error_response("Node ID is required", 400)

        if agg_function not in ['count', 'sum', 'avg']:
            return create_error_response("Invalid aggregation function", 400)
        
        query = f"""
        MATCH (n)-[*1..{depth}]-(m)
        WHERE id(n) = '{node_id}'
        RETURN {agg_function}(m.{agg_property}) as result
        """
        result = execute_sulpher_query(query)
        aggregation_result = result[0]['result']
        links = {
            "node": {"href": url_for('get_node_properties', node_id=node_id)},
            "subgraph": {"href": url_for('get_subgraph')}
        }
        response = create_resource_response("neighborhood_aggregate", {
            "node_id": node_id,
            "depth": depth,
            "property": agg_property,
            "aggregation": agg_function,
            "result": aggregation_result
        }, links)
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Unexpected error in get_neighborhood_aggregate: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)

@app.route('/api/v1/graph/statistics', methods=['GET'])
def get_graph_statistics() -> Tuple[Response, int]:
    try:
        queries = [
            "MATCH (n) RETURN count(n) as node_count",
            "MATCH ()-[r]->() RETURN count(r) as edge_count",
            "MATCH (n) RETURN avg(size((n)-[]->())) as avg_out_degree"
        ]
        stats = {}
        for query in queries:
            result = execute_sulpher_query(query)
            stats.update(result[0])
        
        links = {
            "nodes": {"href": url_for('search_nodes')},
            "query": {"href": url_for('create_graph_query')}
        }
        response = create_resource_response("graph_statistics", stats, links)
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Unexpected error in get_graph_statistics: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)

@app.route('/api/v1/graph/<node_ref>/in', methods=['GET'])
def get_incoming_edges(node_ref: str) -> Tuple[Response, int]:
    try:
        query = f"""
        MATCH (n)<-[r]-(m)
        WHERE id(n) = '{node_ref}'
        RETURN m, type(r) as relationship_type, properties(r) as relationship_properties
        """
        result = execute_sulpher_query(query)
        incoming = [
            {
                "source": {
                    "id": r['m']['id'],
                    "properties": r['m']
                },
                "relationship": {
                    "type": r['relationship_type'],
                    "properties": r['relationship_properties']
                },
                "target": node_ref
            }
            for r in result
        ]
        links = {
            "node": {"href": url_for('get_node_properties', node_id=node_ref)},
            "outgoing": {"href": url_for('get_outgoing_edges', node_ref=node_ref)}
        }
        response = create_collection_response("incoming_edges", incoming, links)
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Unexpected error in get_incoming_edges: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)


def execute_sulpher_query(query: str) -> List[Dict[str, Any]]:
    sulpher_query = SulpherQuery(query)
    asyncio.run(execute_graph_query(sulpher_query))
    return sulpher_query.result

# Validation helpers
def validate_entity_name(entity: str) -> None:
    if not re.match(r'^[a-zA-Z0-9_]+$', entity):
        raise RServError("Invalid entity name", status_code=400)

def validate_id(id: Any) -> None:
    if not isinstance(id, int) or id <= 0:
        raise RServError("Invalid ID", status_code=400)

def validate_query(query: str) -> None:
    if not re.match(r'^(BFS|DFS)?\s*MATCH\s*\(.*\).*$', query):
        raise RServError("Invalid query format", status_code=400)

# Dynamic schema validator
class DynamicValidator:
    def __init__(self, schemas: Dict[str, Any], schema_name: str):
        self.schemas = schemas
        self.schema_name = schema_name

    def validate(self, entity: str, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        if entity not in self.schemas:
            return False, [f"No schema defined for entity type: {entity}"]

        schema = self.schemas[entity]
        errors = []

        for field, rules in schema.items():
            if rules.get("required", True) and field not in data:
                errors.append(f"Missing required field: {field}")
            elif field in data:
                value = data[field]
                field_type = rules["type"]

                if field_type == "string":
                    if not isinstance(value, str):
                        errors.append(f"Field {field} must be a string")
                    elif "max_length" in rules and len(value) > rules["max_length"]:
                        errors.append(f"Field {field} exceeds maximum length of {rules['max_length']}")
                    elif "regex" in rules and not re.match(rules["regex"], value):
                        errors.append(f"Field {field} does not match the required pattern: {rules['regex']}")
                elif field_type == "integer":
                    if not isinstance(value, int):
                        errors.append(f"Field {field} must be an integer")
                    elif "min" in rules and value < rules["min"]:
                        errors.append(f"Field {field} must be greater than or equal to {rules['min']}")
                    elif "max" in rules and value > rules["max"]:
                        errors.append(f"Field {field} must be less than or equal to {rules['max']}")
                elif field_type == "float":
                    if not isinstance(value, (int, float)):
                        errors.append(f"Field {field} must be a number")
                    elif "min" in rules and value < rules["min"]:
                        errors.append(f"Field {field} must be greater than or equal to {rules['min']}")
                    elif "max" in rules and value > rules["max"]:
                        errors.append(f"Field {field} must be less than or equal to {rules['max']}")
                elif field_type == "boolean":
                    if not isinstance(value, bool):
                        errors.append(f"Field {field} must be a boolean")
                elif field_type == "datetime":
                    try:
                        datetime.fromisoformat(value)
                    except (ValueError, TypeError):
                        errors.append(f"Field {field} must be a valid ISO format datetime string")
                elif field_type == "date":
                    try:
                        datetime.strptime(value, "%Y-%m-%d")
                    except (ValueError, TypeError):
                        errors.append(f"Field {field} must be a valid date string in YYYY-MM-DD format")
                elif field_type == "json":
                    if not isinstance(value, (dict, list)):
                        errors.append(f"Field {field} must be a valid JSON object or array")
                
                if "foreign_key" in rules:
                    fk_entity = rules["foreign_key"]["entity"]
                    fk_field = rules["foreign_key"]["field"]
                    fk_file = os.path.join(BASE_DIR, self.schema_name, fk_entity, f"{value}.json")
                    if not os.path.exists(fk_file):
                        errors.append(f"Foreign key constraint failed: {fk_entity} with {fk_field}={value} does not exist")

                if "unique" in rules and rules["unique"] and field in data:
                    entity_dir = get_entity_dir(entity)
                    for filename in os.listdir(entity_dir):
                        if filename.endswith(".json") and filename != f"{value}.json":
                            file_path = os.path.join(entity_dir, filename)
                            with open(file_path, "r") as f:
                                existing_data = json.load(f)
                            if existing_data.get(field) == value:
                                errors.append(f"Field {field} must be unique")
                                break

        return len(errors) == 0, errors

validator = DynamicValidator(schemas, config['schema_name'])

# Cache management
def invalidate_cache(entity: str) -> None:
    """Invalidate cache entries related to the given entity."""
    for key in list(cache.keys()):
        if entity in key:
            del cache[key]

async def cleanup_expired_data() -> None:
    """Cleanup expired queries and cache entries."""
    while True:
        try:
            now = time.time()
            # Clean up expired queries
            expired_queries = [qid for qid, query in query_storage.items() 
                               if query.stats['end_time'] and now - query.stats['end_time'] > config['graph_query_ttl']]
            for qid in expired_queries:
                del query_storage[qid]
            
            # Clean up expired cache entries
            if isinstance(cache, TTLCache):
                # TTLCache automatically handles expiration
                pass
            elif isinstance(cache, redis.Redis):
                # Redis requires explicit key deletion
                expired_cache = [key for key in cache.keys() if now - cache.ttl(key) > config['cache_ttl']]
                for key in expired_cache:
                    cache.delete(key)
            
            await asyncio.sleep(3600)  # Run cleanup every hour
        except Exception as e:
            logger.error(f"Error in cleanup task: {str(e)}")
            await asyncio.sleep(60)  # Wait a minute before retrying if there's an error


async def execute_graph_query(query: SulpherQuery) -> None:
    try:
        query.execute(graph)  # Assuming 'graph' is your graph data structure
    except Exception as e:
        query.status = 'failed'
        query.result = str(e)







@app.route('/api/v1/graph/subgraph', methods=['POST'])
def get_subgraph() -> Tuple[Response, int]:
    try:
        data = request.json
        node_id = data.get('node_id')
        depth = data.get('depth', 1)

        if not node_id:
            return create_error_response("Node ID is required", 400)

        query = f"""
        MATCH (n)-[r*1..{depth}]-(m)
        WHERE id(n) = '{node_id}'
        RETURN n, r, m
        """
        result = execute_sulpher_query(query)
        subgraph_data = {
            "nodes": [r['n'] for r in result] + [r['m'] for r in result],
            "relationships": [rel for r in result for rel in r['r']]
        }
        links = {
            "center_node": {"href": url_for('get_node_properties', node_id=node_id)}
        }
        response = create_resource_response("subgraph", subgraph_data, links)
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Unexpected error in get_subgraph: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)





# Cache management
def invalidate_cache(entity: str) -> None:
    """Invalidate cache entries related to the given entity."""
    for key in list(cache.keys()):
        if entity in key:
            del cache[key]

async def cleanup_expired_data() -> None:
    """Cleanup expired queries and cache entries."""
    while True:
        try:
            now = time.time()
            # Clean up expired queries
            expired_queries = [qid for qid, query in query_storage.items() 
                               if query.stats['end_time'] and now - query.stats['end_time'] > config['graph_query_ttl']]
            for qid in expired_queries:
                del query_storage[qid]
            
            # Clean up expired cache entries
            if isinstance(cache, TTLCache):
                # TTLCache automatically handles expiration
                pass
            elif isinstance(cache, redis.Redis):
                # Redis requires explicit key deletion
                expired_cache = [key for key in cache.keys() if now - cache.ttl(key) > config['cache_ttl']]
                for key in expired_cache:
                    cache.delete(key)
            
            await asyncio.sleep(3600)  # Run cleanup every hour
        except Exception as e:
            logger.error(f"Error in cleanup task: {str(e)}")
            await asyncio.sleep(60)  # Wait a minute before retrying if there's an error



async def execute_graph_query(query: SulpherQuery) -> None:
    try:
        query.execute(graph)  # Assuming 'graph' is your graph data structure
    except Exception as e:
        query.status = 'failed'
        query.result = str(e)


# Cache management
def invalidate_cache(entity: str) -> None:
    """Invalidate cache entries related to the given entity."""
    for key in list(cache.keys()):
        if entity in key:
            del cache[key]



async def cleanup_expired_data() -> None:
    """Cleanup expired queries and cache entries."""
    while True:
        try:
            now = time.time()
            # Clean up expired queries
            expired_queries = [qid for qid, query in query_storage.items() 
                               if query.stats['end_time'] and now - query.stats['end_time'] > config['graph_query_ttl']]
            for qid in expired_queries:
                del query_storage[qid]
            
            # Clean up expired cache entries
            if isinstance(cache, TTLCache):
                # TTLCache automatically handles expiration
                pass
            elif isinstance(cache, redis.Redis):
                # Redis requires explicit key deletion
                expired_cache = [key for key in cache.keys() if now - cache.ttl(key) > config['cache_ttl']]
                for key in expired_cache:
                    cache.delete(key)
            
            await asyncio.sleep(3600)  # Run cleanup every hour
        except Exception as e:
            logger.error(f"Error in cleanup task: {str(e)}")
            await asyncio.sleep(60)  # Wait a minute before retrying if there's an error



async def execute_graph_query(query: SulpherQuery) -> None:
    try:
        query.execute(graph)  # Assuming 'graph' is your graph data structure
    except Exception as e:
        query.status = 'failed'
        query.result = str(e)




@app.route('/api/v1/graph/<node_ref>/out', methods=['GET'])
def get_outgoing_edges(node_ref: str) -> Tuple[Response, int]:
    try:
        query = f"""
        MATCH (n)-[r]->(m)
        WHERE id(n) = '{node_ref}'
        RETURN m, type(r) as relationship_type, properties(r) as relationship_properties
        """
        result = execute_sulpher_query(query)
        outgoing = [
            {
                "source": node_ref,
                "relationship": {
                    "type": r['relationship_type'],
                    "properties": r['relationship_properties']
                },
                "target": {
                    "id": r['m']['id'],
                    "properties": r['m']
                }
            }
            for r in result
        ]
        links = {
            "node": {"href": url_for('get_node_properties', node_id=node_ref)},
            "incoming": {"href": url_for('get_incoming_edges', node_ref=node_ref)}
        }
        response = create_collection_response("outgoing_edges", outgoing, links)
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Unexpected error in get_outgoing_edges: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)


# Cache management
def invalidate_cache(entity: str) -> None:
    """Invalidate cache entries related to the given entity."""
    for key in list(cache.keys()):
        if entity in key:
            del cache[key]

async def cleanup_expired_data() -> None:
    """Cleanup expired queries and cache entries."""
    while True:
        try:
            now = time.time()
            # Clean up expired queries
            expired_queries = [qid for qid, query in query_storage.items() 
                               if query.stats['end_time'] and now - query.stats['end_time'] > config['graph_query_ttl']]
            for qid in expired_queries:
                del query_storage[qid]
            
            # Clean up expired cache entries
            if isinstance(cache, TTLCache):
                # TTLCache automatically handles expiration
                pass
            elif isinstance(cache, redis.Redis):
                # Redis requires explicit key deletion
                expired_cache = [key for key in cache.keys() if now - cache.ttl(key) > config['cache_ttl']]
                for key in expired_cache:
                    cache.delete(key)
            
            await asyncio.sleep(3600)  # Run cleanup every hour
        except Exception as e:
            logger.error(f"Error in cleanup task: {str(e)}")
            await asyncio.sleep(60)  # Wait a minute before retrying if there's an error

# Start the cleanup task
asyncio.create_task(cleanup_expired_data())

# Graph indexing functions (using graph.data and graph.index)
def load_graph_from_file(file_path: str) -> Dict[str, Dict[str, Any]]:
    """Loads the adjacency list from a file."""
    graph = defaultdict(lambda: {'type': None, 'neighbors': []})
    with open(file_path, 'r') as f:
        for line in f:
            parts = line.strip().split(':')
            node_id = parts[0].strip()
            neighbors = [n.strip() for n in parts[1].split()]
            graph[node_id] = {'type': node_id.split(':')[0], 'neighbors': neighbors}
    return graph

def load_index_from_file(file_path: str) -> Dict[str, int]:
    """Loads the adjacency index from a file."""
    index = {}
    with open(file_path, 'r') as f:
        for line in f:
            parts = line.strip().split(':')
            node_id = parts[0].strip()
            offset = int(parts[1].strip())
            index[node_id] = offset
    return index

async def save_graph_to_file(file_path: str) -> None:
    """Saves the adjacency list to disk."""
    with open(file_path, 'w') as f:
        for node_id, data in graph.items():
            neighbors = ' '.join(data['neighbors'])
            f.write(f"{node_id}:{neighbors}\n")

async def save_index_to_file(file_path: str) -> None:
    """Saves the adjacency index to disk."""
    with open(file_path, 'w') as f:
        for node_id, offset in index.items():
            f.write(f"{node_id}:{offset}\n")

def build_graph_index(graph: Dict[str, Dict[str, Any]]) -> None:
    """Builds the inverted index from the graph."""
    global index

    for node_id, data in graph.items():
        index[data['type']].add(node_id)
        for key, value in data.items():
            if isinstance(value, dict) and value.get('type') == 'REF':
                index[value['entity']].add(node_id)
                index[f"relationship:{key}"].add(node_id)

def update_graph_index(entity: str, id: int, data: Dict[str, Any], operation: str) -> None:
    """Updates the index based on graph modifications."""
    global index

    node_id = f"{entity}:{id}"
    if operation == 'create' or operation == 'update':
        index[data['type']].add(node_id)
        for key, value in data.items():
            if isinstance(value, dict) and value.get('type') == 'REF':
                index[value['entity']].add(node_id)
                index[f"relationship:{key}"].add(node_id)
    elif operation == 'delete':
        index[data['type']].discard(node_id)
        for key, value in data.items():
            if isinstance(value, dict) and value.get('type') == 'REF':
                index[value['entity']].discard(node_id)
                index[f"relationship:{key}"].discard(node_id)

def save_graph_index(index_file: str) -> None:
    """Saves the index to disk."""
    with open(index_file, 'w') as f:
        json.dump(index, f)

def load_graph_index(index_file: str) -> None:
    """Loads the index from disk."""
    global index

    if os.path.exists(index_file):
        with open(index_file, 'r') as f:
            index = json.load(f)

def _find_matching_nodes(self, graph: Dict[str, Dict[str, Any]], node_pattern: Dict[str, Any]) -> List[str]:
    matching_nodes = []
    if config['rserv_graph'] == 'indexed':
        # Index-based lookup
        matching_nodes = set(index.get(node_pattern['type'], set()))
        for prop, value in node_pattern['props'].items():
            matching_nodes &= set(index.get(f"{prop}:{value}", set()))
    else:
        # Default behavior: Iterate through all nodes
        for node, data in graph.items():
            if (node_pattern['type'] is None or data['type'] == node_pattern['type']) and \
               all(data.get(k) == v for k, v in node_pattern['props'].items()):
                matching_nodes.append(node)
    return list(matching_nodes)  # Return a list of matching node IDs

    
if __name__ == '__main__':

    print("////////////// rserv {RSERV_VERSION} // a simple REST prototyping server //////////////")
    print("---------------------------------------------------------")
    print("Server Configuration:")
    print(f"  Host: {config['host']}")
    print(f"  Port: {config['port']}")
    print(f"  Schema: {config['schema_name']}")

    print("\nGraph Configuration:")
    print(f"  Mode: {'Enabled' if config['graph_enabled'] else 'Disabled'}")
    print(f"  Type: {config['rserv_graph']}")
    print(f"  Query TTL: {config['graph_query_ttl']} seconds")

    print("\nCache Configuration:")
    print(f"  Type: {config['cache_type']}")
    print(f"  TTL: {config['cache_ttl']} seconds")

    print("\nOther Configuration:")
    print(f"  Full-text search: {'Enabled' if config['fulltext_enabled'] else 'Disabled'}")
    print(f"  Cascading delete: {'Enabled' if config['cascading_delete'] else 'Disabled'}")
    print(f"  REF embed depth: {config['ref_embed_depth']}")
    print(f"  Patch null handling: {config['patch_null']}")
    print(f"  Max query depth: {config['max_query_depth']}")
        
    # Build initial full-text index and graph
    if config['fulltext_enabled'] or config['graph_enabled']:
        for entity in os.listdir(os.path.join(BASE_DIR, config['schema_name'])):
            entity_dir = get_entity_dir(entity)
            for filename in os.listdir(entity_dir):
                if filename.endswith('.json'):
                    with open(os.path.join(entity_dir, filename), 'r') as f:
                        data = json.load(f)
                        if config['fulltext_enabled']:
                            index_document(entity, data['id'], data)
                        if config['rserv_graph'] == 'indexed':
                            update_graph_index(entity, data['id'], data, 'create')
                            update_graph(entity, data['id'], data)
    if config['rserv_graph'] == 'indexed':
        load_graph_index(config['adjacency_index_file'])
        graph = load_graph_from_file(config['adjacency_list_file'])
    app.run(host=config['host'], port=config['port'], debug=True)


