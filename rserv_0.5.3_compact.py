import os
import sys
import json
import time
import uuid
import asyncio
import logging
import atexit
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict, deque
from flask import Flask, request, jsonify, Response, abort, url_for
import re
from datetime import datetime, timedelta
import functools
import fcntl
import multiprocessing
from cachetools import TTLCache
import threading
import signal
shutdown_handlers = []
def register_shutdown_handler(handler):
    shutdown_handlers.append(handler)
def signal_handler(signum, frame):
    try:
        logger.info(f"Received signal {signum}, shutting down gracefully...")
    except Exception:
        pass
    for handler in shutdown_handlers:
        try:
            handler()
        except Exception as e:
            try:
                logger.error(f"Error in shutdown handler: {e}")
            except Exception:
                pass
    sys.exit(0)
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
@app.before_request
def validate_request_and_initialization():
    if not initialization_complete.is_set():
        if not initialization_complete.wait(timeout=30):
            return jsonify({
                "error": {
                    "message": "Server is still initializing, please try again",
                    "status": 503
                }
            }), 503
    if request.method in ['POST', 'PUT', 'PATCH']:
        if not request.is_json and request.content_length > 0:
            return jsonify({
                "error": {
                    "message": "Content-Type must be application/json",
                    "status": 400
                }
            }), 400
        if request.content_length and request.content_length > 1024 * 1024:
            try:
                _ = request.get_json(force=True)
            except:
                return jsonify({
                    "error": {
                        "message": "Invalid or oversized JSON payload",
                        "status": 400
                    }
                }), 400
BASE_DIR = 'data'
SCHEMA_DIR = 'schema'
DEFAULT_SCHEMA = 'default'
RSERV_VERSION = "0.5.3"
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
    'max_cascade_deletions': 10000,
    'max_cascade_work': 100000,
    'max_entity_size': 1048576,
    'rserv_graph': 'indexed',
    'adjacency_list_file': 'graph.data',
    'adjacency_index_file': 'graph.index',
    'graph_query_ttl': 86400,
    'graph_result_ttl': 3600,
    'fulltext_enabled': False,
    'ref_embed_depth': 3,
    'max_query_depth': 10,
    'max_embed_depth': 10,
    'cache_type': 'ttlcache',
    'redis_host': 'localhost',
    'redis_port': 6379,
    'graph_cycle_detection': 'warn'
}
config = {k.lower(): v for k, v in DEFAULT_CONFIG.items()}
for key, value in os.environ.items():
    key_lower = key.lower()
    if key_lower in config:
        if isinstance(config[key_lower], bool):
            config[key_lower] = value.lower() in ('true', '1', 'yes')
        elif isinstance(config[key_lower], int):
            config[key_lower] = int(value)
        else:
            config[key_lower] = value
DEBUG_LOCKS = config.get('debug_locks', False)
try:
    import redis
    if config['cache_type'] == 'redis':
        redis_pool = redis.ConnectionPool(
            host=config['redis_host'], 
            port=config['redis_port'],
            max_connections=50,
            decode_responses=True
        )
        cache = redis.Redis(connection_pool=redis_pool)
        logger.info(f"Using Redis cache with connection pool at {config['redis_host']}:{config['redis_port']}")
        atexit.register(lambda: redis_pool.disconnect())
        register_shutdown_handler(lambda: redis_pool.disconnect())
    else:
        cache = TTLCache(maxsize=1024, ttl=config['cache_ttl'])
        logger.info(f"Using in-memory TTLCache with TTL {config['cache_ttl']} seconds")
except ImportError:
    cache = TTLCache(maxsize=1024, ttl=config['cache_ttl'])
    logger.info("Redis module not available. Using in-memory TTLCache.")
def cache_get(key):
    if isinstance(cache, TTLCache):
        with LockWithTimeout(cache_lock, "cache_lock"):
            return cache.get(key)
    else:
        try:
            value = cache.get(key)
            return json.loads(value) if value else None
        except (json.JSONDecodeError, redis.RedisError, AttributeError) as e:
            logger.warning(f"Cache get error for key {key}: {str(e)}")
            return None
def cache_set(key, value):
    if isinstance(cache, TTLCache):
        with LockWithTimeout(cache_lock, "cache_lock"):
            cache[key] = value
    else:
        try:
            cache.set(key, json.dumps(value), ex=config['cache_ttl'])
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {str(e)}")
def cache_exists(key):
    if isinstance(cache, TTLCache):
        return key in cache
    else:
        try:
            return bool(cache.exists(key))
        except (KeyError, redis.RedisError, ConnectionError) as e:
            logger.debug(f"Cache exists check failed: {e}")
            return False
def cache_delete_pattern(pattern):
    if isinstance(cache, TTLCache):
        with LockWithTimeout(cache_lock, "cache_lock"):
            keys_to_delete = [key for key in list(cache.keys()) if str(key).startswith(f"{pattern}:")]
            for key in keys_to_delete:
                cache.pop(key, None)
    else:
        try:
            cursor = 0
            while True:
                cursor, keys = cache.scan(cursor, match=f"{pattern}:*", count=100)
                if keys:
                    cache.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.error(f"Error deleting cache pattern {pattern}: {str(e)}")
graph = defaultdict(dict)
fulltext_index = defaultdict(set)
fulltext_reverse_index = defaultdict(set)
query_storage = {}
index = defaultdict(set)
next_id_lock = threading.RLock()
MAX_STORED_QUERIES = 1000
QUERY_EXPIRY_TIME = 3600
last_cleanup_time = 0
graph_lock = threading.RLock()
fulltext_lock = threading.RLock()
index_lock = threading.RLock()
query_lock = threading.RLock()
cache_lock = threading.RLock()
cleanup_lock = threading.RLock()
LOCK_TIMEOUT = 5.0
class LockWithTimeout:
    def __init__(self, lock, name):
        self.lock = lock
        self.name = name
    def __enter__(self):
        validate_lock_order(self.name)
        if not self.lock.acquire(timeout=LOCK_TIMEOUT):
            release_lock_tracking(self.name)
            raise RServError(f"Could not acquire {self.name} after {LOCK_TIMEOUT}s", 503)
        return self.lock
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()
        release_lock_tracking(self.name)
_held_locks = threading.local()
def validate_lock_order(lock_name):
    lock_order = [
        'next_id_lock',
        'cleanup_timer_lock',
        'cleanup_lock',
        'graph_lock',
        'index_lock',
        'fulltext_lock',
        'query_lock',
        'cache_lock'
    ]
    if not hasattr(_held_locks, 'stack'):
        _held_locks.stack = []
    if _held_locks.stack:
        last_lock = _held_locks.stack[-1]
        try:
            last_index = lock_order.index(last_lock)
            new_index = lock_order.index(lock_name)
            if new_index < last_index:
                logger.warning(f"Lock order violation: {lock_name} after {last_lock}")
                if DEBUG_LOCKS:
                    raise RuntimeError(f"Lock order violation: {lock_name} after {last_lock}")
        except ValueError:
            logger.warning(f"Lock {lock_name} not in lock hierarchy - consider adding it")
            pass
    _held_locks.stack.append(lock_name)
def release_lock_tracking(lock_name):
    if hasattr(_held_locks, 'stack') and _held_locks.stack:
        if _held_locks.stack[-1] == lock_name:
            _held_locks.stack.pop()
        else:
            logger.error(f"Lock order violation: expected {lock_name} but found {_held_locks.stack[-1]}")
            if DEBUG_LOCKS:
                raise RuntimeError(f"Lock order violation: expected to release {lock_name} but {_held_locks.stack[-1]} is on top")
initialization_complete = threading.Event()
def cleanup_old_queries():
    with LockWithTimeout(query_lock, "query_lock"):
        current_time = time.time()
        expired_queries = []
        for query_id, query in query_storage.items():
            if hasattr(query, 'stats') and query.stats.get('end_time'):
                if current_time - query.stats['end_time'] > QUERY_EXPIRY_TIME:
                    expired_queries.append(query_id)
        for query_id in expired_queries:
            del query_storage[query_id]
            cache_delete_pattern(f"query:{query_id}")
        if len(query_storage) > MAX_STORED_QUERIES:
            completed_queries = [
                (q_id, q.stats.get('end_time', 0)) 
                for q_id, q in query_storage.items() 
                if hasattr(q, 'status') and q.status == 'completed'
            ]
            completed_queries.sort(key=lambda x: x[1])
            to_remove = len(query_storage) - MAX_STORED_QUERIES // 2
            for q_id, _ in completed_queries[:to_remove]:
                del query_storage[q_id]
                cache_delete_pattern(f"query:{q_id}")
def cleanup_orphaned_graph_nodes():
    if config['rserv_graph'] != 'indexed':
        return
    try:
        with LockWithTimeout(graph_lock, "graph_lock"):
            with LockWithTimeout(index_lock, "index_lock"):
                orphaned_nodes = []
                nodes_checked = 0
                for node_key in list(graph.keys()):
                    nodes_checked += 1
                    try:
                        entity, id_str = node_key.split(':', 1)
                        entity_id = int(id_str)
                        file_path = get_entity_file(entity, entity_id)
                        if not os.path.exists(file_path):
                            orphaned_nodes.append(node_key)
                    except (ValueError, OSError):
                        orphaned_nodes.append(node_key)
                for node_key in orphaned_nodes:
                    if node_key in graph:
                        del graph[node_key]
                    for other_node in list(graph.keys()):
                        if node_key in graph[other_node]:
                            del graph[other_node][node_key]
                if orphaned_nodes:
                    logger.info(
                        f"Graph cleanup: removed {len(orphaned_nodes)} orphaned nodes "
                        f"out of {nodes_checked} checked"
                    )
                    save_graph_to_file(config['adjacency_list_file'])
                    save_graph_index(config['adjacency_index_file'])
    except Exception as e:
        logger.error(f"Error during graph cleanup: {e}")
cleanup_timer = None
cleanup_timer_lock = threading.RLock()
def start_periodic_cleanup():
    global cleanup_timer
    def cleanup_and_reschedule():
        try:
            cleanup_old_queries()
        except Exception as e:
            logger.error(f"Error in periodic query cleanup: {e}")
        try:
            cleanup_orphaned_graph_nodes()
        except Exception as e:
            logger.error(f"Error in periodic graph cleanup: {e}")
        finally:
            global cleanup_timer
            with LockWithTimeout(cleanup_timer_lock, "cleanup_timer_lock"):
                if cleanup_timer:
                    cleanup_timer.cancel()
                cleanup_timer = threading.Timer(300.0, cleanup_and_reschedule)
                cleanup_timer.daemon = True
                cleanup_timer.start()
    with LockWithTimeout(cleanup_timer_lock, "cleanup_timer_lock"):
        if cleanup_timer:
            cleanup_timer.cancel()
        cleanup_timer = threading.Timer(300.0, cleanup_and_reschedule)
        cleanup_timer.daemon = True
        cleanup_timer.start()
    logger.info("Started periodic query cleanup (every 5 minutes)")
def stop_periodic_cleanup():
    global cleanup_timer
    with LockWithTimeout(cleanup_timer_lock, "cleanup_timer_lock"):
        if cleanup_timer:
            cleanup_timer.cancel()
atexit.register(stop_periodic_cleanup)
def acquire_lock_with_timeout(lock, lock_name, timeout=LOCK_TIMEOUT):
    if DEBUG_LOCKS:
        logger.debug(f"Thread {threading.current_thread().name} attempting to acquire {lock_name}")
    acquired = lock.acquire(timeout=timeout)
    if not acquired:
        error_msg = f"Could not acquire {lock_name} after {timeout}s - possible deadlock"
        logger.error(error_msg)
        raise RServError(error_msg, status_code=503)
    if DEBUG_LOCKS:
        logger.debug(f"Thread {threading.current_thread().name} acquired {lock_name}")
    return True
def with_lock(lock, lock_name):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            acquire_lock_with_timeout(lock, lock_name)
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                lock.release()
                if DEBUG_LOCKS:
                    logger.debug(f"Thread {threading.current_thread().name} released {lock_name}")
        return wrapper
    return decorator
def detect_potential_deadlock():
    held_locks = []
    thread_id = threading.current_thread().ident
    for lock_name, lock_obj in [
        ('graph_lock', graph_lock),
        ('fulltext_lock', fulltext_lock),
        ('index_lock', index_lock),
        ('query_lock', query_lock)
    ]:
        if hasattr(lock_obj, '_owner') and lock_obj._owner == thread_id:
            held_locks.append(lock_name)
    if DEBUG_LOCKS and len(held_locks) > 1:
        logger.warning(f"Thread {threading.current_thread().name} holds multiple locks: {held_locks}")
    return held_locks
def safe_batch_operation(operations, lock, lock_name):
    with LockWithTimeout(lock, lock_name):
        if DEBUG_LOCKS:
            logger.debug(f"Batch operation starting with {lock_name}")
        results = []
        for operation in operations:
            try:
                result = operation()
                results.append(('success', result))
            except Exception as e:
                results.append(('error', e))
        if DEBUG_LOCKS:
            logger.debug(f"Batch operation completed with {lock_name}")
        return results
class RServError(Exception):
    def __init__(self, message: str, status_code: int = 400, payload: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.payload = payload
    def to_dict(self) -> Dict[str, Any]:
        error_dict = dict(self.payload or ())
        error_dict['message'] = self.message
        error_dict['status_code'] = self.status_code
        return error_dict
@app.errorhandler(RServError)
def handle_rserv_error(error: RServError) -> Tuple[Response, int]:
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response
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
def load_schemas(schema_name: str) -> Dict[str, Any]:
    schema_dir = os.path.join(SCHEMA_DIR, schema_name)
    schemas = {}
    if os.path.exists(schema_dir):
        for filename in os.listdir(schema_dir):
            if filename.endswith('.json'):
                entity_name = os.path.splitext(filename)[0]
                try:
                    with open(os.path.join(schema_dir, filename), 'r') as f:
                        schemas[entity_name] = json.load(f)
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping invalid schema file {filename}: {e}")
                except Exception as e:
                    logger.error(f"Error loading schema {filename}: {e}")
    return schemas
schemas = load_schemas(config['schema_name'])
def get_entity_dir(entity: str) -> str:
    entity_dir = os.path.join(BASE_DIR, config['schema_name'], entity)
    os.makedirs(entity_dir, exist_ok=True)
    return entity_dir
def sanitize_path(entity: str, id: int) -> str:
    safe_entity = os.path.basename(str(entity).replace('..', '').replace('/', '').replace('\\', ''))
    safe_id = os.path.basename(str(id).replace('..', '').replace('/', '').replace('\\', ''))
    if not safe_entity or not re.match(r'^[a-zA-Z0-9_]+$', safe_entity):
        raise RServError(f"Invalid entity name: {entity}", 400)
    safe_path = os.path.join(BASE_DIR, config['schema_name'], safe_entity, f"{safe_id}.json")
    real_base = os.path.realpath(BASE_DIR)
    real_path = os.path.realpath(os.path.dirname(safe_path))
    if not real_path.startswith(real_base):
        raise RServError("Invalid path detected", 400)
    return safe_path
def get_entity_file(entity: str, id: int) -> str:
    return sanitize_path(entity, id)
def get_entity_data(entity: str, id: int) -> Optional[Dict[str, Any]]:
    file_path = get_entity_file(entity, id)
    if not os.path.exists(file_path):
        return None
    with open(file_path, 'r') as f:
        return json.load(f)
def get_next_id(entity: str) -> int:
    entity_dir = get_entity_dir(entity)
    id_file = os.path.join(entity_dir, f"{entity}_next_id.json")
    with LockWithTimeout(next_id_lock, "next_id_lock"):
        try:
            import fcntl
            with open(id_file, 'a+') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.seek(0)
                    content = f.read().strip()
                    if not content:
                        current_id = 0
                    else:
                        try:
                            current_id = json.loads(content)
                            if not isinstance(current_id, int) or current_id < 0:
                                raise ValueError("Invalid ID format")
                        except (json.JSONDecodeError, ValueError) as e:
                            logger.warning(f"Corrupted ID file for {entity}, reinitializing: {e}")
                            current_id = 0
                    next_id = current_id + 1
                    f.seek(0)
                    f.truncate()
                    json.dump(next_id, f)
                    f.flush()
                    os.fsync(f.fileno())
                    return next_id
                finally:
                    pass
        except ImportError:
            logger.warning("fcntl not available, ID generation only thread-safe (not process-safe)")
            try:
                fd = os.open(id_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, 'w') as f:
                    f.write('1')
                    return 1
            except FileExistsError:
                pass
            except Exception as e:
                logger.error(f"Error creating ID file for entity {entity}: {str(e)}")
                raise RServError(f"Error generating ID for entity {entity}", status_code=500)
            with open(id_file, 'r+') as f:
                try:
                    current_id = json.load(f)
                    if not isinstance(current_id, int) or current_id < 0:
                        raise ValueError("Invalid ID format")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Corrupted ID file for {entity}, reinitializing: {e}")
                    current_id = 0
                next_id = current_id + 1
                temp_file = f"{id_file}.tmp"
                with open(temp_file, 'w') as tmp_f:
                    json.dump(next_id, tmp_f)
                os.replace(temp_file, id_file)
                return next_id
        except Exception as e:
            logger.error(f"Error updating next ID for entity {entity}: {str(e)}")
            raise RServError(f"Error generating ID for entity {entity}", status_code=500)
@app.route('/api/v1/<entity>', methods=['POST'])
def create_entity(entity: str) -> Tuple[Response, int]:
    file_path = None
    temp_path = None
    new_id = None
    try:
        validate_entity_name(entity)
        data = request.json
        if not data:
            raise RServError("No input data provided", status_code=400)
        new_id = get_next_id(entity)
        data['id'] = new_id
        is_valid, errors = validator.validate(entity, data)
        if not is_valid:
            return jsonify({"error": "Validation failed", "details": errors}), 400
        MAX_ENTITY_SIZE = config.get("max_entity_size", 1048576)
        json_str = json.dumps(data)
        if len(json_str) > MAX_ENTITY_SIZE:
            raise RServError(
                f"Entity too large: {len(json_str)} bytes (max: {MAX_ENTITY_SIZE})",
                status_code=413
            )
        file_path = get_entity_file(entity, new_id)
        temp_path = f"{file_path}.tmp"
        with open(temp_path, 'w') as f:
            f.write(json_str)
        try:
            if config['rserv_graph'] == 'indexed':
                with LockWithTimeout(graph_lock, "graph_lock"):
                    with LockWithTimeout(index_lock, "index_lock"):
                        update_graph_index(entity, new_id, data, 'create')
                        update_graph(entity, new_id, data)
                        os.rename(temp_path, file_path)
                        temp_path = None
                        save_graph_index(config['adjacency_index_file'])
                        save_graph_to_file(config['adjacency_list_file'])
                        if config['fulltext_enabled']:
                            with LockWithTimeout(fulltext_lock, "fulltext_lock"):
                                index_document(entity, new_id, data)
            else:
                os.rename(temp_path, file_path)
                temp_path = None
                if config['fulltext_enabled']:
                    with LockWithTimeout(fulltext_lock, "fulltext_lock"):
                        index_document(entity, new_id, data)
        except Exception as e:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            if file_path and os.path.exists(file_path) and not temp_path:
                try:
                    os.remove(file_path)
                except:
                    pass
            raise
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
        cache_key = f"{entity}:{id}"
        cached_data = cache_get(cache_key)
        if cached_data:
            logger.info(f"Retrieved resource of entity {entity} with id {id} from cache")
            return jsonify(cached_data), 200
        file_path = get_entity_file(entity, id)
        if not os.path.exists(file_path):
            raise RServError(f"Resource of entity {entity} with id {id} not found", status_code=404)
        with open(file_path, 'r') as f:
            data = json.load(f)
        lookup = request.args.get('lookup')
        if lookup:
            embed_depth = request.args.get('embed_depth', config['ref_embed_depth'], type=int)
            embed_depth = validate_embed_depth(embed_depth)
            data = populate_document(entity, data, lookup.split(','), max_depth=embed_depth)
        cache_set(cache_key, data)
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
        is_valid, errors = validator.validate(entity, data)
        if not is_valid:
            return jsonify({"error": "Validation failed", "details": errors}), 400
        MAX_ENTITY_SIZE = config.get("max_entity_size", 1048576)
        json_str = json.dumps(data)
        if len(json_str) > MAX_ENTITY_SIZE:
            raise RServError(
                f"Entity too large: {len(json_str)} bytes (max: {MAX_ENTITY_SIZE})",
                status_code=413
            )
        with open(file_path, 'w') as f:
            f.write(json_str)
        if config['rserv_graph'] == 'indexed':
            with LockWithTimeout(graph_lock, "graph_lock"):
                with LockWithTimeout(index_lock, "index_lock"):
                    update_graph_index(entity, id, data, 'update')
                    update_graph(entity, id, data)
                    save_graph_index(config['adjacency_index_file'])
                    save_graph_to_file(config['adjacency_list_file'])
                    if config['fulltext_enabled']:
                        with LockWithTimeout(fulltext_lock, "fulltext_lock"):
                            index_document(entity, id, data)
        else:
            if config['fulltext_enabled']:
                with LockWithTimeout(fulltext_lock, "fulltext_lock"):
                    index_document(entity, id, data)
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
        if config['rserv_graph'] == 'indexed':
            with LockWithTimeout(graph_lock, "graph_lock"):
                with LockWithTimeout(index_lock, "index_lock"):
                    update_graph_index(entity, id, existing_data, 'update')
                    update_graph(entity, id, existing_data)
                    save_graph_index(config['adjacency_index_file'])
                    save_graph_to_file(config['adjacency_list_file'])
                    if config['fulltext_enabled']:
                        with LockWithTimeout(fulltext_lock, "fulltext_lock"):
                            index_document(entity, id, existing_data)
        else:
            if config['fulltext_enabled']:
                with LockWithTimeout(fulltext_lock, "fulltext_lock"):
                    index_document(entity, id, existing_data)
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
            deleted_refs = cascade_delete(entity, id, force=False)
            logger.info(f"Cascade deleted {entity} with id {id} ({len(deleted_refs)} total)")
            return jsonify({
                "message": f"{entity} with id {id} deleted successfully",
                "cascaded_deletes": deleted_refs
            }), 200
        graph_data = None
        if config['rserv_graph'] == 'indexed':
            with LockWithTimeout(graph_lock, "graph_lock"):
                with LockWithTimeout(index_lock, "index_lock"):
                    graph_data = get_entity_data(entity, id)
        temp_file = f"{file_path}.deleted"
        try:
            os.rename(file_path, temp_file)
            if config['rserv_graph'] == 'indexed' and graph_data:
                with LockWithTimeout(graph_lock, "graph_lock"):
                    with LockWithTimeout(index_lock, "index_lock"):
                        update_graph_index(entity, id, graph_data, 'delete')
                        remove_from_graph(entity, id)
                        save_graph_index(config['adjacency_index_file'])
                        save_graph_to_file(config['adjacency_list_file'])
                        if config['fulltext_enabled']:
                            with LockWithTimeout(fulltext_lock, "fulltext_lock"):
                                remove_from_index(entity, id)
            else:
                if config['fulltext_enabled']:
                    with LockWithTimeout(fulltext_lock, "fulltext_lock"):
                        remove_from_index(entity, id)
            try:
                os.remove(temp_file)
            except:
                pass
            invalidate_cache(entity)
            logger.info(f"Deleted {entity} with id {id}")
            return jsonify({
                "message": f"{entity} with id {id} deleted successfully",
                "cascaded_deletes": [f"{entity}:{id}"]
            }), 200
        except Exception as e:
            logger.error(f"Error during deletion, rolling back: {str(e)}")
            if os.path.exists(temp_file) and not os.path.exists(file_path):
                try:
                    os.rename(temp_file, file_path)
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback file {file_path}: {rollback_error}")
            raise
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in delete_entity: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
def cascade_delete(entity: str, id: int, force: bool = False) -> List[str]:
    MAX_CASCADE_DELETIONS = config.get('max_cascade_deletions', 10000)
    MAX_CASCADE_WORK = config.get('max_cascade_work', 100000)
    old_force = config.get('force_cascade_delete', False)
    old_cascade = config.get('cascading_delete', False)
    try:
        if force:
            config['force_cascade_delete'] = True
        config['cascading_delete'] = True
        file_path = get_entity_file(entity, id)
        if not os.path.exists(file_path):
            raise RServError(f"Resource of entity {entity} with id {id} not found", status_code=404)
        deleted_refs = []
        to_check = [(entity, id)]
        checked = set()
        files_examined = 0
        while to_check:
            if len(deleted_refs) >= MAX_CASCADE_DELETIONS:
                logger.error(
                    f"Cascade deletion limit ({MAX_CASCADE_DELETIONS}) reached after examining {files_examined} files. "
                    "Possible circular references or too many connected entities."
                )
                raise RServError(
                    f"Cascade deletion aborted: would delete more than {MAX_CASCADE_DELETIONS} entities. "
                    f"Examined {files_examined} files. Check for circular references or increase 'max_cascade_deletions' config.",
                    status_code=500
                )
            if files_examined >= MAX_CASCADE_WORK:
                logger.error(
                    f"Cascade work limit ({MAX_CASCADE_WORK} files) reached. "
                    f"Would have deleted {len(deleted_refs)} entities. Operation too expensive."
                )
                raise RServError(
                    f"Cascade deletion aborted: examined {files_examined} files (limit: {MAX_CASCADE_WORK}). "
                    f"Would delete {len(deleted_refs)} entities. Operation too expensive for synchronous execution. "
                    "Consider: (1) manually deleting referencing entities first, (2) increasing 'max_cascade_work' config, "
                    "or (3) implementing async cascade deletion.",
                    status_code=409
                )
            current_entity, current_id = to_check.pop(0)
            key = f"{current_entity}:{current_id}"
            if key in checked:
                continue
            checked.add(key)
            deleted_refs.append(key)
            if config['cascading_delete']:
                try:
                    schema_path = os.path.join(BASE_DIR, config['schema_name'])
                    for e in os.listdir(schema_path):
                        entity_dir = get_entity_dir(e)
                        if os.path.isdir(entity_dir):
                            try:
                                for filename in os.listdir(entity_dir):
                                    if filename.endswith('.json') and not filename.endswith('_next_id.json'):
                                        files_examined += 1
                                        if files_examined >= MAX_CASCADE_WORK:
                                            break
                                        try:
                                            file_path = os.path.join(entity_dir, filename)
                                            with open(file_path, 'r') as f:
                                                other_data = json.load(f)
                                            for k, value in other_data.items():
                                                if isinstance(value, dict) and value.get('type') == 'REF':
                                                    if value.get('entity') == current_entity and value.get('id') == current_id:
                                                        to_check.append((e, other_data['id']))
                                                        break
                                        except Exception as file_error:
                                            logger.warning(f"Error reading {filename} during cascade: {file_error}")
                                if files_examined >= MAX_CASCADE_WORK:
                                    break
                            except OSError as dir_error:
                                logger.warning(f"Error accessing directory {entity_dir}: {dir_error}")
                except OSError as schema_error:
                    logger.error(f"Error accessing schema directory: {schema_error}")
                    raise RServError("Error scanning entities for cascade deletion", status_code=500)
        logger.info(
            f"Cascade delete collected {len(deleted_refs)} entities after examining {files_examined} files. "
            f"Starting: {entity}:{id}"
        )
        deleted_files = []
        try:
            for ref in deleted_refs:
                e, i = ref.split(':')
                file = get_entity_file(e, int(i))
                if os.path.exists(file):
                    temp_file = f"{file}.deleted"
                    os.rename(file, temp_file)
                    deleted_files.append((file, temp_file))
            if config['rserv_graph'] == 'indexed':
                with LockWithTimeout(graph_lock, "graph_lock"):
                    with LockWithTimeout(index_lock, "index_lock"):
                        for ref in deleted_refs:
                            e, i = ref.split(':')
                            remove_from_graph(e, int(i))
            if config['fulltext_enabled']:
                with LockWithTimeout(fulltext_lock, "fulltext_lock"):
                    for ref in deleted_refs:
                        e, i = ref.split(':')
                        remove_from_index(e, int(i))
            for original_path, temp_path in deleted_files:
                try:
                    os.remove(temp_path)
                except:
                    pass
            invalidate_cache(entity)
            logger.info(
                f"Cascade deleted {len(deleted_refs)} entities (examined {files_examined} files) "
                f"starting from {entity}:{id}"
            )
            return deleted_refs
        except Exception as e:
            logger.error(f"Cascade deletion failed after collecting {len(deleted_refs)} entities, rolling back: {e}")
            for original_path, temp_path in deleted_files:
                try:
                    if os.path.exists(temp_path) and not os.path.exists(original_path):
                        os.rename(temp_path, original_path)
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback file {original_path}: {rollback_error}")
            raise
    finally:
        config['force_cascade_delete'] = old_force
        config['cascading_delete'] = old_cascade
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
        is_valid, errors = validator.validate(entity, data)
        if not is_valid:
            return jsonify({"error": "Validation failed", "details": errors}), 400
        with open(file_path, 'w') as f:
            json.dump(data, f)
        if config['rserv_graph'] == 'indexed':
            with LockWithTimeout(graph_lock, "graph_lock"):
                with LockWithTimeout(index_lock, "index_lock"):
                    update_graph_index(entity, id, data, 'create')
                    update_graph(entity, id, data)
                    save_graph_index(config['adjacency_index_file'])
                    save_graph_to_file(config['adjacency_list_file'])
                    if config['fulltext_enabled']:
                        with LockWithTimeout(fulltext_lock, "fulltext_lock"):
                            index_document(entity, id, data)
        else:
            if config['fulltext_enabled']:
                with LockWithTimeout(fulltext_lock, "fulltext_lock"):
                    index_document(entity, id, data)
        invalidate_cache(entity)
        logger.info(f"Saved resource of entity {entity} with id {id}")
        return jsonify({"message": f"Resource of entity {entity} saved successfully with id {id}"}), 201
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in save_entity: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
def get_pagination_params() -> Tuple[int, int]:
    page = max(1, request.args.get('page', 1, type=int))
    per_page = max(1, min(100, request.args.get('per_page', config['default_page_size'], type=int)))
    validate_pagination_params(page, per_page)
    return page, per_page
def get_sorting_params() -> List[Tuple[str, str]]:
    sort_params = request.args.get('sort', 'id:asc')
    return validate_sort_params(sort_params)
def sort_entities(entities: List[Dict[str, Any]], sort_params: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    def multi_field_comparator(a: Dict[str, Any], b: Dict[str, Any]) -> int:
        for field, order in sort_params:
            a_val = a.get(field)
            b_val = b.get(field)
            if a_val is None and b_val is None:
                continue
            if a_val is None:
                return 1 if order == 'asc' else -1
            if b_val is None:
                return -1 if order == 'asc' else 1
            try:
                if type(a_val) != type(b_val):
                    a_val = str(a_val)
                    b_val = str(b_val)
                if a_val != b_val:
                    if order == 'asc':
                        return (a_val > b_val) - (a_val < b_val)
                    else:
                        return (a_val < b_val) - (a_val > b_val)
            except TypeError:
                a_val = str(a_val)
                b_val = str(b_val)
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
        cache_key = f"{entity}:list:{page}:{per_page}:{sort_params}"
        cached_data = cache_get(cache_key)
        if cached_data:
            logger.info(f"Retrieved paginated list of {entity} from cache")
            return jsonify(cached_data), 200
        entities = get_all_entities(entity)
        sorted_entities = sort_entities(entities, sort_params)
        paginated_results = paginate_results(sorted_entities, page, per_page)
        cache_set(cache_key, paginated_results)
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
        if filename.endswith('.json') and not filename.endswith('_next_id.json'):
            with open(os.path.join(entity_dir, filename), 'r') as f:
                entities.append(json.load(f))
    return entities
def tokenize(text: str) -> List[str]:
    if not text:
        return []
    if not isinstance(text, str):
        text = str(text)
    return re.findall(r'\w+', text.lower())
def index_document(entity: str, doc_id: int, content: Dict[str, Any]) -> None:
    tokens = set(tokenize(json.dumps(content)))
    doc_ref = f"{entity}:{doc_id}"
    with LockWithTimeout(fulltext_lock, "fulltext_lock"):
        for token in tokens:
            fulltext_index[token].add(doc_ref)
        fulltext_reverse_index[doc_ref] = tokens
def remove_from_index(entity: str, doc_id: int) -> None:
    doc_ref = f"{entity}:{doc_id}"
    with LockWithTimeout(fulltext_lock, "fulltext_lock"):
        if doc_ref in fulltext_reverse_index:
            tokens = fulltext_reverse_index[doc_ref]
            for token in tokens:
                if token in fulltext_index:
                    fulltext_index[token].discard(doc_ref)
                    if not fulltext_index[token]:
                        del fulltext_index[token]
            del fulltext_reverse_index[doc_ref]
def search_fulltext(query: str, limit: int = 10) -> List[str]:
    query_tokens = tokenize(query)
    results = defaultdict(int)
    with LockWithTimeout(fulltext_lock, "fulltext_lock"):
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
        validate_search_query(query)
        limit = data.get('limit', 10)
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            raise RServError("Limit must be an integer between 1 and 100", status_code=400)
        results = search_fulltext(query, limit)
        response = create_collection_response("search_results", results)
        return jsonify(response), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in fulltext_search: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
def update_graph(entity: str, id: int, data: Dict[str, Any]) -> None:
    if config['rserv_graph'] == 'disabled':
        return
    with LockWithTimeout(graph_lock, "graph_lock"):
        node_id = f"{entity}:{id}"
        remove_from_graph(entity, id)
        for key, value in data.items():
            if isinstance(value, dict) and value.get('type') == 'REF':
                ref_entity = value.get('entity')
                ref_id = value.get('id')
                if ref_entity and ref_id:
                    target_node = f"{ref_entity}:{ref_id}"
                    graph[node_id][target_node] = key
                    graph[target_node][node_id] = f"reverse_{key}"
def remove_from_graph(entity: str, id: int) -> None:
    if config['rserv_graph'] == 'disabled':
        return
    with LockWithTimeout(graph_lock, "graph_lock"):
        node_id = f"{entity}:{id}"
        for source_node in list(graph.keys()):
            if node_id in graph[source_node]:
                del graph[source_node][node_id]
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
            ref_doc = get_entity_data(ref_entity, ref_id)
            if ref_doc:
                doc[field] = populate_document(ref_entity, ref_doc, lookup_fields, depth + 1, max_depth)
    return doc
def validate_entity_name(entity: str) -> None:
    if not re.match(r'^[a-zA-Z0-9_]+$', entity):
        raise RServError("Invalid entity name", status_code=400)
def validate_id(id: Any) -> None:
    if not isinstance(id, int) or id <= 0:
        raise RServError("Invalid ID", status_code=400)
def validate_query(query: str) -> None:
    if not re.match(r'^(BFS|DFS)?\s*MATCH\s*\(.*\).*$', query):
        raise RServError("Invalid query format", status_code=400)
def validate_pagination_params(page: int, per_page: int) -> None:
    if page < 1:
        raise RServError("Page must be 1 or greater", status_code=400)
    if per_page < 1 or per_page > 100:
        raise RServError("Per page must be between 1 and 100", status_code=400)
def validate_sort_params(sort_params: str) -> List[Tuple[str, str]]:
    if not sort_params:
        return [('id', 'asc')]
    valid_orders = {'asc', 'desc'}
    parsed_params = []
    for param in sort_params.split(','):
        if ':' not in param:
            raise RServError(f"Invalid sort parameter format: {param}. Use 'field:order'", status_code=400)
        field, order = param.split(':', 1)
        field = field.strip()
        order = order.strip().lower()
        if not re.match(r'^[a-zA-Z0-9_]+$', field):
            raise RServError(f"Invalid sort field name: {field}", status_code=400)
        if order not in valid_orders:
            raise RServError(f"Invalid sort order: {order}. Must be 'asc' or 'desc'", status_code=400)
        parsed_params.append((field, order))
    return parsed_params
def validate_search_query(query: str, max_length: int = 1000) -> None:
    if not query or not query.strip():
        raise RServError("Search query cannot be empty", status_code=400)
    if len(query) > max_length:
        raise RServError(f"Search query too long (max {max_length} characters)", status_code=400)
    if query.count('*') > 10 or query.count('?') > 10:
        raise RServError("Too many wildcards in search query", status_code=400)
def validate_embed_depth(depth: Any) -> int:
    try:
        depth = int(depth)
        if depth < 0:
            raise RServError("Embed depth must be non-negative", status_code=400)
        if depth > config.get('max_embed_depth', 10):
            raise RServError(f"Embed depth exceeds maximum of {config.get('max_embed_depth', 10)}", status_code=400)
        return depth
    except (TypeError, ValueError):
        raise RServError("Embed depth must be an integer", status_code=400)
class DynamicValidator:
    def __init__(self, schemas: Dict[str, Any], schema_name: str):
        self.schemas = schemas
        self.schema_name = schema_name
    def validate(self, entity: str, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        if entity not in self.schemas:
            return True, []
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
                    elif "regex" in rules and not re.fullmatch(rules["regex"], value):
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
                    current_id = data.get('id')
                    for filename in os.listdir(entity_dir):
                        if filename.endswith(".json") and not filename.endswith("_next_id.json"):
                            try:
                                file_id = int(filename[:-5])
                                if current_id and file_id == current_id:
                                    continue
                                file_path = os.path.join(entity_dir, filename)
                                with open(file_path, "r") as f:
                                    existing_data = json.load(f)
                                if existing_data.get(field) == value:
                                    errors.append(f"Field {field} must be unique")
                                    break
                            except ValueError:
                                continue
        return len(errors) == 0, errors
validator = DynamicValidator(schemas, config['schema_name'])
def invalidate_cache(entity: str) -> None:
    cache_delete_pattern(entity)
class SulpherQuery:
    def __init__(self, query_string: str, max_depth: int = None):
        self.query_string = query_string
        self.query_id = str(uuid.uuid4())
        self.status = 'pending'
        self.result = None
        self.stats = {'nodes_traversed': 0, 'start_time': None, 'end_time': None}
        self.parsed_query = None
        self.max_depth = max_depth or config['max_query_depth']
    def parse(self):
        pattern = r'((?:BFS|DFS) )?MATCH ((?:\([^\)]+\)(?:-\[[^\]]+\]->)?)+)(?: WHERE (.+))? RETURN (.+)'
        match = re.match(pattern, self.query_string)
        if not match:
            raise ValueError("Invalid Sulpher query format")
        algorithm, path_pattern, where_clause, return_clause = match.groups()
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
        where_conditions = self._parse_where_clause(where_clause) if where_clause else None
        return_items = [item.strip() for item in return_clause.split(',')]
        self.parsed_query = {
            'algorithm': algorithm.strip() if algorithm else 'BFS',
            'path': parsed_path,
            'where': where_conditions,
            'return': return_items
        }
        return self.parsed_query
    def _parse_properties(self, element_string: str) -> Dict[str, Any]:
        if not element_string or '{' not in element_string:
            return {}
        props_match = re.search(r'\{([^\}]+)\}', element_string)
        if not props_match:
            return {}
        props = {}
        prop_pairs = props_match.group(1).split(',')
        for pair in prop_pairs:
            key, value = pair.strip().split(':', 1)
            key = key.strip().strip('"\'')
            value = value.strip().strip('"\'')
            if value.lower() == 'true':
                value = True
            elif value.lower() == 'false':
                value = False
            elif value.isdigit():
                value = int(value)
            props[key] = value
        return props
    def _parse_where_clause(self, where_clause: str) -> List[Dict[str, Any]]:
        conditions = []
        condition_parts = where_clause.split(' AND ')
        for condition in condition_parts:
            match = re.match(r'^\s*(.+?)\s*(<=|>=|!=|=|<|>)\s*(.+?)\s*$', condition)
            if match:
                var_path, operator, value = match.groups()
                conditions.append({
                    'var_path': var_path.strip(),
                    'operator': operator.strip(),
                    'value': value.strip().strip('"\'')
                })
            else:
                logger.warning(f"Could not parse WHERE condition: {condition}")
        return conditions
    def execute(self):
        self.stats['start_time'] = time.time()
        self.status = 'running'
        try:
            parsed = self.parse()
            start_node_pattern = parsed['path'][0]['node']
            with LockWithTimeout(graph_lock, "graph_lock"):
                import copy
                graph_snapshot = copy.deepcopy(graph)
            matching_start_nodes = self._find_matching_nodes(graph_snapshot, start_node_pattern)
            results = []
            for start_node in matching_start_nodes:
                if parsed['algorithm'] == 'BFS':
                    paths = self._bfs_traverse(start_node, parsed['path'], graph_snapshot)
                else:
                    paths = self._dfs_traverse(start_node, parsed['path'], graph_snapshot=graph_snapshot)
                if parsed['where']:
                    paths = self._apply_where_conditions(paths, parsed['where'])
                for path in paths:
                    result = self._apply_return_clause(path, parsed['return'])
                    results.append(result)
            self.result = results
            self.status = 'completed'
        except Exception as e:
            self.status = 'failed'
            self.result = {'error': str(e)}
        finally:
            self.stats['end_time'] = time.time()
            cache_key = f"query:{self.query_id}"
            cache_set(cache_key, (self.result, self.stats))
            global last_cleanup_time
            current_time = time.time()
            should_cleanup = False
            with LockWithTimeout(cleanup_lock, "cleanup_lock"):
                if current_time - last_cleanup_time > 60:
                    last_cleanup_time = current_time
                    should_cleanup = True
            if should_cleanup:
                cleanup_old_queries()
    def _has_cycle_from_node(self, graph: Dict[str, Dict[str, Any]], start_node: str, 
                            visited: set, rec_stack: set) -> bool:
        visited.add(start_node)
        rec_stack.add(start_node)
        neighbors = graph.get(start_node, {})
        for target_node, relationship_type in neighbors.items():
            if target_node not in visited:
                if self._has_cycle_from_node(graph, target_node, visited, rec_stack):
                    return True
            elif target_node in rec_stack:
                if config.get('graph_cycle_detection', 'warn') == 'error':
                    raise RServError(f"Cycle detected: {start_node} -> {target_node} via {relationship_type}", 400)
                elif config.get('graph_cycle_detection', 'warn') == 'warn':
                    logger.warning(f"Cycle detected: {start_node} -> {target_node} via {relationship_type}")
                return True
        rec_stack.remove(start_node)
        return False
    def _check_cycles(self, graph: Dict[str, Dict[str, Any]]) -> bool:
        cycle_mode = config.get('graph_cycle_detection', 'warn')
        if cycle_mode == 'disable' or cycle_mode == 'ignore':
            return False
        visited = set()
        rec_stack = set()
        for node in graph:
            if node not in visited:
                if self._has_cycle_from_node(graph, node, visited, rec_stack):
                    return True
        return False
    def _find_matching_nodes(self, graph: Dict[str, Dict[str, Any]], node_pattern: Dict[str, Any]) -> List[str]:
        matching_nodes = []
        if config['rserv_graph'] == 'indexed':
            with LockWithTimeout(index_lock, "index_lock"):
                matching_nodes = set(index.get(node_pattern['type'], set()))
                for prop, value in node_pattern['props'].items():
                    matching_nodes &= set(index.get(f"{prop}:{value}", set()))
        else:
            for node, data in graph.items():
                if (node_pattern['type'] is None or data.get('type') == node_pattern['type']) and \
                   all(data.get(k) == v for k, v in node_pattern['props'].items()):
                    matching_nodes.append(node)
        return list(matching_nodes)
    def _bfs_traverse(self, start_node: str, path_pattern: List[Dict[str, Any]], graph_snapshot: Dict[str, Dict[str, Any]] = None) -> List[List[Dict[str, Any]]]:
        if graph_snapshot is None:
            with LockWithTimeout(graph_lock, "graph_lock"):
                graph_snapshot = dict(graph)
        paths = []
        queue = deque([(start_node, 0, [])])
        visited = set()
        max_iterations = 10000
        iterations = 0
        while queue and iterations < max_iterations:
            iterations += 1
            current_node, pattern_index, current_path = queue.popleft()
            if len(current_path) > self.max_depth:
                continue
            if (current_node, pattern_index) in visited:
                continue
            visited.add((current_node, pattern_index))
            self.stats['nodes_traversed'] += 1
            current_path = current_path + [{'node': current_node, 'data': graph_snapshot.get(current_node, {})}]
            if pattern_index >= len(path_pattern) - 1:
                paths.append(current_path)
                continue
            next_pattern = path_pattern[pattern_index + 1]
            for neighbor, edge_type in graph_snapshot.get(current_node, {}).items():
                if self._matches_relationship(edge_type, next_pattern['relationship']):
                    neighbor_data = graph_snapshot.get(neighbor, {})
                    if self._matches_node(neighbor, neighbor_data, next_pattern['node']):
                        queue.append((neighbor, pattern_index + 1, current_path))
        if iterations >= max_iterations:
            logger.error(f"BFS traversal hit iteration limit - possible infinite loop or very large graph")
            raise RServError("Query execution exceeded safety limits", 500)
        return paths
    def _dfs_traverse(self, start_node: str, path_pattern: List[Dict[str, Any]], 
                      pattern_index: int = 0, current_path: List[Dict[str, Any]] = None, 
                      visited: set = None, graph_snapshot: Dict[str, Dict[str, Any]] = None) -> List[List[Dict[str, Any]]]:
        if graph_snapshot is None:
            import copy
            with LockWithTimeout(graph_lock, "graph_lock"):
                graph_snapshot = copy.deepcopy(graph)
        if current_path is None:
            current_path = []
        if visited is None:
            visited = set()
        if (start_node, pattern_index) in visited:
            return []
        visited.add((start_node, pattern_index))
        self.stats['nodes_traversed'] += 1
        current_path = current_path + [{'node': start_node, 'data': graph_snapshot.get(start_node, {})}]
        if pattern_index >= len(path_pattern) - 1:
            return [current_path]
        paths = []
        next_pattern = path_pattern[pattern_index + 1]
        for neighbor, edge_type in graph_snapshot.get(start_node, {}).items():
            if self._matches_relationship(edge_type, next_pattern['relationship']):
                neighbor_data = graph_snapshot.get(neighbor, {})
                if self._matches_node(neighbor, neighbor_data, next_pattern['node']):
                    sub_paths = self._dfs_traverse(neighbor, path_pattern, pattern_index + 1, 
                                                   current_path, visited.copy(), graph_snapshot)
                    paths.extend(sub_paths)
        return paths
    def _matches_node(self, node_id: str, node_data: Dict[str, Any], 
                      node_pattern: Dict[str, Any]) -> bool:
        if node_pattern['type'] and node_data.get('type') != node_pattern['type']:
            return False
        for key, value in node_pattern['props'].items():
            if node_data.get(key) != value:
                return False
        return True
    def _matches_relationship(self, edge_type: str, rel_pattern: Dict[str, Any]) -> bool:
        if not rel_pattern['type']:
            return True
        return edge_type == rel_pattern['type']
    def _apply_where_conditions(self, paths: List[List[Dict[str, Any]]], 
                                conditions: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        filtered_paths = []
        for path in paths:
            match = True
            for condition in conditions:
                var_name, prop_path = condition['var_path'].split('.', 1)
                value = None
                for node in path:
                    if node['node'].split(':')[0] == var_name:
                        value = node['data'].get(prop_path)
                        break
                if not self._evaluate_condition(value, condition['operator'], condition['value']):
                    match = False
                    break
            if match:
                filtered_paths.append(path)
        return filtered_paths
    def _evaluate_condition(self, value: Any, operator: str, compare_value: str) -> bool:
        if value is None:
            return False
        try:
            if isinstance(value, int):
                compare_value = int(compare_value)
            elif isinstance(value, float):
                compare_value = float(compare_value)
        except (ValueError, TypeError):
            return False
        if operator == '=':
            return value == compare_value
        elif operator == '<':
            return value < compare_value
        elif operator == '>':
            return value > compare_value
        elif operator == '<=':
            return value <= compare_value
        elif operator == '>=':
            return value >= compare_value
        elif operator == '!=':
            return value != compare_value
        return False
    def _apply_return_clause(self, path: List[Dict[str, Any]], 
                             return_items: List[str]) -> Dict[str, Any]:
        result = {}
        for item in return_items:
            if '.' in item:
                var_name, prop_path = item.split('.', 1)
                for node in path:
                    if node['node'].split(':')[0] == var_name:
                        result[item] = node['data'].get(prop_path)
                        break
            else:
                for node in path:
                    if node['node'].split(':')[0] == item:
                        result[item] = node['data']
                        break
        return result
@app.route('/api/v1/graph/query', methods=['POST'])
def execute_graph_query() -> Tuple[Response, int]:
    try:
        if config['rserv_graph'] == 'disabled':
            raise RServError("Graph functionality is disabled", status_code=400)
        data = request.json
        if not data or 'query' not in data:
            raise RServError("No query provided", status_code=400)
        query_string = data['query']
        validate_query(query_string)
        max_depth = data.get('max_depth', config['max_query_depth'])
        query = SulpherQuery(query_string, max_depth)
        with LockWithTimeout(query_lock, "query_lock"):
            query_storage[query.query_id] = query
        query.execute()
        response = create_resource_response("query_result", {
            "query_id": query.query_id,
            "status": query.status,
            "result": query.result,
            "stats": query.stats
        })
        return jsonify(response), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in execute_graph_query: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)
@app.route('/api/v1/graph/query/<query_id>', methods=['GET'])
def get_query_result(query_id: str) -> Tuple[Response, int]:
    try:
        cache_key = f"query:{query_id}"
        cached_result = cache_get(cache_key)
        if cached_result:
            result, stats = cached_result
            response = create_resource_response("query_result", {
                "query_id": query_id,
                "status": "completed",
                "result": result,
                "stats": stats
            })
            return jsonify(response), 200
        with LockWithTimeout(query_lock, "query_lock"):
            if query_id not in query_storage:
                raise RServError("Query not found", status_code=404)
            query = query_storage[query_id]
            response_data = {
                "query_id": query_id,
                "status": query.status,
                "result": query.result,
                "stats": query.stats
            }
        response = create_resource_response("query_result", response_data)
        return jsonify(response), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in get_query_result: {str(e)}")
        return create_error_response("An unexpected error occurred", 500)
@app.route('/api/v1/<entity>', methods=['GET'])
def get_entities(entity: str) -> Tuple[Response, int]:
    try:
        validate_entity_name(entity)
        page, per_page = get_pagination_params()
        sort_params = get_sorting_params()
        filters = {}
        for key, value in request.args.items():
            if key not in ['page', 'per_page', 'sort']:
                filters[key] = value
        filter_str = ','.join(f"{k}={v}" for k, v in sorted(filters.items()))
        cache_key = f"{entity}:collection:{filter_str}:{page}:{per_page}:{sort_params}"
        cached_data = cache_get(cache_key)
        if cached_data:
            logger.info(f"Retrieved filtered collection of {entity} from cache")
            return jsonify(cached_data), 200
        entity_dir = get_entity_dir(entity)
        filtered_entities = []
        if os.path.exists(entity_dir):
            for filename in os.listdir(entity_dir):
                if filename.endswith('.json') and not filename.endswith('_next_id.json'):
                    try:
                        with open(os.path.join(entity_dir, filename), 'r') as f:
                            data = json.load(f)
                        if all(str(data.get(k)) == str(v) for k, v in filters.items()):
                            filtered_entities.append(data)
                    except Exception as e:
                        logger.warning(f"Error reading {filename}: {str(e)}")
        sorted_entities = sort_entities(filtered_entities, sort_params)
        total = len(sorted_entities)
        start = (page - 1) * per_page
        end = start + per_page
        response = {
            "data": sorted_entities[start:end],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": max(1, (total + per_page - 1) // per_page)
            },
            "filters": filters,
            "sort": ','.join(f"{field}:{order}" for field, order in sort_params)
        }
        base_url = request.base_url
        query_params = request.query_string.decode()
        response["links"] = {
            "self": f"{base_url}?{query_params}",
            "first": url_for('get_entities', entity=entity, page=1, per_page=per_page, **filters),
            "last": url_for('get_entities', entity=entity, page=response["pagination"]["pages"], per_page=per_page, **filters)
        }
        if page > 1:
            response["links"]["prev"] = url_for('get_entities', entity=entity, page=page-1, per_page=per_page, **filters)
        if page < response["pagination"]["pages"]:
            response["links"]["next"] = url_for('get_entities', entity=entity, page=page+1, per_page=per_page, **filters)
        cache_set(cache_key, response)
        logger.info(f"Retrieved filtered collection of {entity} (filters: {filters}, page: {page})")
        return jsonify(response), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in get_entities: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
@app.route('/api/v1/<entity>/search', methods=['GET'])
def search_entity_field(entity: str) -> Tuple[Response, int]:
    try:
        validate_entity_name(entity)
        field = request.args.get('field', 'name')
        query = request.args.get('q', '').strip()
        match_type = request.args.get('match', 'contains')
        if not query:
            raise RServError("Query parameter 'q' is required", status_code=400)
        if match_type not in ['contains', 'starts', 'ends', 'exact']:
            raise RServError("Invalid match type. Use: contains, starts, ends, exact", status_code=400)
        if not re.match(r'^[a-zA-Z0-9_]+$', field):
            raise RServError("Invalid field name", status_code=400)
        page, per_page = get_pagination_params()
        sort_params = get_sorting_params()
        cache_key = f"{entity}:search:{field}:{query}:{match_type}:{page}:{per_page}:{sort_params}"
        cached_data = cache_get(cache_key)
        if cached_data:
            return jsonify(cached_data), 200
        matching_entities = []
        entity_dir = get_entity_dir(entity)
        if os.path.exists(entity_dir):
            for filename in os.listdir(entity_dir):
                if filename.endswith('.json') and not filename.endswith('_next_id.json'):
                    try:
                        with open(os.path.join(entity_dir, filename), 'r') as f:
                            data = json.load(f)
                        if field in data:
                            field_value = data[field]
                            matched = False
                            if isinstance(field_value, bool):
                                query_bool = query.lower() in ('true', '1', 'yes')
                                matched = (field_value == query_bool)
                            elif isinstance(field_value, (int, float)):
                                try:
                                    query_numeric = float(query) if '.' in query else int(query)
                                    matched = (field_value == query_numeric)
                                except ValueError:
                                    field_value_str = str(field_value).lower()
                                    query_lower = query.lower()
                                    if match_type == 'contains':
                                        matched = query_lower in field_value_str
                                    elif match_type == 'starts':
                                        matched = field_value_str.startswith(query_lower)
                                    elif match_type == 'ends':
                                        matched = field_value_str.endswith(query_lower)
                                    elif match_type == 'exact':
                                        matched = field_value_str == query_lower
                            else:
                                field_value_str = str(field_value).lower()
                                query_lower = query.lower()
                                if match_type == 'contains':
                                    matched = query_lower in field_value_str
                                elif match_type == 'starts':
                                    matched = field_value_str.startswith(query_lower)
                                elif match_type == 'ends':
                                    matched = field_value_str.endswith(query_lower)
                                elif match_type == 'exact':
                                    matched = field_value_str == query_lower
                            if matched:
                                matching_entities.append(data)
                    except Exception as e:
                        logger.warning(f"Error searching {filename}: {str(e)}")
        sorted_entities = sort_entities(matching_entities, sort_params)
        paginated_results = paginate_results(sorted_entities, page, per_page)
        paginated_results['search'] = {
            'field': field,
            'query': query,
            'match_type': match_type,
            'matches': len(matching_entities)
        }
        cache_set(cache_key, paginated_results)
        logger.info(f"Searched {entity} for '{query}' in field '{field}' (match: {match_type})")
        return jsonify(paginated_results), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in search_entity_field: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
@app.route('/api/v1/graph/statistics', methods=['GET'])
def get_graph_statistics() -> Tuple[Response, int]:
    try:
        if config['rserv_graph'] == 'disabled':
            raise RServError("Graph functionality is disabled", status_code=400)
        with LockWithTimeout(graph_lock, "graph_lock"):
            node_count = len(graph)
            edge_count = sum(len(neighbors) for neighbors in graph.values())
            avg_degree = edge_count / node_count if node_count > 0 else 0
            type_counts = defaultdict(int)
            relationship_counts = defaultdict(int)
            for node_id, neighbors in graph.items():
                entity_type = node_id.split(':', 1)[0] if ':' in node_id else 'unknown'
                type_counts[entity_type] += 1
                for _, rel_type in neighbors.items():
                    relationship_counts[rel_type] += 1
        if config['rserv_graph'] == 'indexed':
            with LockWithTimeout(index_lock, "index_lock"):
                index_stats = {
                    "indexed_properties": len([k for k in index.keys() if ':' in k]),
                    "indexed_types": len([k for k in index.keys() if ':' not in k])
                }
        else:
            index_stats = {}
        stats = {
            "node_count": node_count,
            "edge_count": edge_count,
            "avg_degree": round(avg_degree, 2),
            "max_degree": max(len(neighbors) for neighbors in graph.values()) if graph else 0,
            "type_distribution": dict(type_counts),
            "relationship_distribution": dict(relationship_counts),
            "graph_mode": config['rserv_graph'],
            "index_stats": index_stats
        }
        response = create_resource_response("graph_statistics", stats)
        return jsonify(response), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in get_graph_statistics: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
@app.route('/api/v1/graph/query/<query_id>/result', methods=['GET'])
def get_query_result_endpoint(query_id: str) -> Tuple[Response, int]:
    try:
        with LockWithTimeout(query_lock, "query_lock"):
            if query_id not in query_storage:
                raise RServError("Query not found", status_code=404)
            query = query_storage[query_id]
            if query.status != 'completed':
                raise RServError(f"Query not completed yet (status: {query.status})", status_code=400)
        response = create_resource_response("query_result", {
            "query_id": query_id,
            "result": query.result,
            "stats": query.stats
        }, {
            "status": {"href": url_for('get_query_result', query_id=query_id)}
        })
        return jsonify(response), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in get_query_result_endpoint: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
@app.route('/api/v1/graph/<node_ref>/in', methods=['GET'])
def get_incoming_edges(node_ref: str) -> Tuple[Response, int]:
    try:
        if config['rserv_graph'] == 'disabled':
            raise RServError("Graph functionality is disabled", status_code=400)
        incoming = []
        with LockWithTimeout(graph_lock, "graph_lock"):
            for source_id, targets in graph.items():
                if node_ref in targets:
                    relationship = targets[node_ref]
                    source_parts = source_id.split(':', 1)
                    if len(source_parts) == 2:
                        source_type, source_entity_id = source_parts
                        try:
                            source_data = get_entity_data(source_type, int(source_entity_id))
                            source_info = {
                                "id": source_id,
                                "type": source_type,
                                "properties": source_data
                            }
                        except:
                            source_info = {"id": source_id}
                    else:
                        source_info = {"id": source_id}
                    incoming.append({
                        "source": source_info,
                        "relationship": relationship,
                        "target": node_ref
                    })
        response = create_collection_response("incoming_edges", incoming, {
            "node": {"href": url_for('get_graph_node', node_id=node_ref)},
            "out": {"href": url_for('get_outgoing_edges', node_ref=node_ref)}
        })
        return jsonify(response), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in get_incoming_edges: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
@app.route('/api/v1/graph/<node_ref>/out', methods=['GET'])
def get_outgoing_edges(node_ref: str) -> Tuple[Response, int]:
    try:
        if config['rserv_graph'] == 'disabled':
            raise RServError("Graph functionality is disabled", status_code=400)
        outgoing = []
        with LockWithTimeout(graph_lock, "graph_lock"):
            if node_ref in graph:
                for target_id, relationship in graph[node_ref].items():
                    target_parts = target_id.split(':', 1)
                    if len(target_parts) == 2:
                        target_type, target_entity_id = target_parts
                        try:
                            target_data = get_entity_data(target_type, int(target_entity_id))
                            target_info = {
                                "id": target_id,
                                "type": target_type,
                                "properties": target_data
                            }
                        except:
                            target_info = {"id": target_id}
                    else:
                        target_info = {"id": target_id}
                    outgoing.append({
                        "source": node_ref,
                        "relationship": relationship,
                        "target": target_info
                    })
        response = create_collection_response("outgoing_edges", outgoing, {
            "node": {"href": url_for('get_graph_node', node_id=node_ref)},
            "in": {"href": url_for('get_incoming_edges', node_ref=node_ref)}
        })
        return jsonify(response), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in get_outgoing_edges: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
@app.route('/api/v1/graph/nodes/<node_id>', methods=['GET'])
def get_graph_node(node_id: str) -> Tuple[Response, int]:
    try:
        if config['rserv_graph'] == 'disabled':
            raise RServError("Graph functionality is disabled", status_code=400)
        parts = node_id.split(':', 1)
        if len(parts) != 2:
            raise RServError("Invalid node ID format. Use 'entity:id'", status_code=400)
        entity_type, entity_id_str = parts
        try:
            entity_id = int(entity_id_str)
        except ValueError:
            raise RServError("Entity ID must be numeric", status_code=400)
        data = get_entity_data(entity_type, entity_id)
        if not data:
            raise RServError("Node not found", status_code=404)
        with LockWithTimeout(graph_lock, "graph_lock"):
            out_degree = len(graph.get(node_id, {}))
            in_degree = sum(1 for _, targets in graph.items() if node_id in targets)
            out_relationships = defaultdict(int)
            if node_id in graph:
                for _, rel_type in graph[node_id].items():
                    out_relationships[rel_type] += 1
            in_relationships = defaultdict(int)
            for _, targets in graph.items():
                if node_id in targets:
                    rel_type = targets[node_id]
                    in_relationships[rel_type] += 1
        node_data = {
            "id": node_id,
            "type": entity_type,
            "properties": data,
            "graph_metadata": {
                "in_degree": in_degree,
                "out_degree": out_degree,
                "total_degree": in_degree + out_degree,
                "in_relationships": dict(in_relationships),
                "out_relationships": dict(out_relationships)
            }
        }
        response = create_resource_response("graph_node", node_data, {
            "self": {"href": url_for('get_graph_node', node_id=node_id)},
            "entity": {"href": url_for('get_entity', entity=entity_type, id=entity_id)},
            "in": {"href": url_for('get_incoming_edges', node_ref=node_id)},
            "out": {"href": url_for('get_outgoing_edges', node_ref=node_id)},
            "neighbors": {"href": url_for('get_node_neighbors', node_id=node_id)},
            "degree": {"href": url_for('get_node_degree', node_id=node_id)}
        })
        return jsonify(response), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in get_graph_node: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
@app.route('/api/v1/graph/nodes/<node_id>/neighbors', methods=['GET'])
def get_node_neighbors(node_id: str) -> Tuple[Response, int]:
    try:
        if config['rserv_graph'] == 'disabled':
            raise RServError("Graph functionality is disabled", status_code=400)
        direction = request.args.get('direction', 'both')
        relationship_type = request.args.get('relationship_type')
        if direction not in ['in', 'out', 'both']:
            raise RServError("Invalid direction. Use: in, out, both", status_code=400)
        neighbors = []
        with LockWithTimeout(graph_lock, "graph_lock"):
            if direction in ['out', 'both']:
                if node_id in graph:
                    for neighbor_id, rel_type in graph[node_id].items():
                        if not relationship_type or rel_type == relationship_type:
                            neighbor_parts = neighbor_id.split(':', 1)
                            if len(neighbor_parts) == 2:
                                try:
                                    neighbor_data = get_entity_data(
                                        neighbor_parts[0], 
                                        int(neighbor_parts[1])
                                    )
                                    neighbor_info = {
                                        "id": neighbor_id,
                                        "type": neighbor_parts[0],
                                        "properties": neighbor_data
                                    }
                                except:
                                    neighbor_info = {"id": neighbor_id}
                            else:
                                neighbor_info = {"id": neighbor_id}
                            neighbors.append({
                                "node": neighbor_info,
                                "relationship": rel_type,
                                "direction": "out"
                            })
            if direction in ['in', 'both']:
                for source_id, targets in graph.items():
                    if node_id in targets:
                        rel_type = targets[node_id]
                        if not relationship_type or rel_type == relationship_type:
                            source_parts = source_id.split(':', 1)
                            if len(source_parts) == 2:
                                try:
                                    source_data = get_entity_data(
                                        source_parts[0], 
                                        int(source_parts[1])
                                    )
                                    source_info = {
                                        "id": source_id,
                                        "type": source_parts[0],
                                        "properties": source_data
                                    }
                                except:
                                    source_info = {"id": source_id}
                            else:
                                source_info = {"id": source_id}
                            neighbors.append({
                                "node": source_info,
                                "relationship": rel_type,
                                "direction": "in"
                            })
        result = {
            "node_id": node_id,
            "neighbor_count": len(neighbors),
            "neighbors": neighbors,
            "filters": {
                "direction": direction,
                "relationship_type": relationship_type
            }
        }
        response = create_resource_response("node_neighbors", result)
        return jsonify(response), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in get_node_neighbors: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
@app.route('/api/v1/graph/nodes/<node_id>/degree', methods=['GET'])
def get_node_degree(node_id: str) -> Tuple[Response, int]:
    try:
        if config['rserv_graph'] == 'disabled':
            raise RServError("Graph functionality is disabled", status_code=400)
        with LockWithTimeout(graph_lock, "graph_lock"):
            out_relationships = defaultdict(int)
            out_degree = 0
            if node_id in graph:
                for _, rel_type in graph[node_id].items():
                    out_relationships[rel_type] += 1
                    out_degree += 1
            in_relationships = defaultdict(int)
            in_degree = 0
            for source_id, targets in graph.items():
                if node_id in targets:
                    rel_type = targets[node_id]
                    in_relationships[rel_type] += 1
                    in_degree += 1
        response = create_resource_response("node_degree", {
            "node_id": node_id,
            "in_degree": in_degree,
            "out_degree": out_degree,
            "total_degree": in_degree + out_degree,
            "in_relationships": dict(in_relationships),
            "out_relationships": dict(out_relationships),
            "is_isolated": (in_degree + out_degree) == 0
        })
        return jsonify(response), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in get_node_degree: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
@app.route('/api/v1/graph/nodes/search', methods=['POST'])
def search_graph_nodes() -> Tuple[Response, int]:
    try:
        if config['rserv_graph'] == 'disabled':
            raise RServError("Graph functionality is disabled", status_code=400)
        search_criteria = request.json
        if not search_criteria:
            raise RServError("Search criteria required", status_code=400)
        entity_type = search_criteria.pop('type', None)
        entity_type_filter = search_criteria.pop('entity_type', entity_type)
        limit = min(search_criteria.pop('limit', 100), 1000)
        matching_nodes = []
        if entity_type_filter and config['rserv_graph'] == 'indexed':
            with LockWithTimeout(index_lock, "index_lock"):
                candidate_nodes = list(index.get(entity_type_filter, set()))
        else:
            with LockWithTimeout(graph_lock, "graph_lock"):
                candidate_nodes = list(graph.keys())
        for node_id in candidate_nodes[:limit * 10]:
            parts = node_id.split(':', 1)
            if len(parts) == 2:
                entity, id_str = parts
                if entity_type_filter and entity != entity_type_filter:
                    continue
                try:
                    entity_id = int(id_str)
                    data = get_entity_data(entity, entity_id)
                    if data:
                        if all(str(data.get(k)) == str(v) for k, v in search_criteria.items()):
                            with LockWithTimeout(graph_lock, "graph_lock"):
                                out_degree = len(graph.get(node_id, {}))
                                in_degree = sum(1 for _, targets in graph.items() if node_id in targets)
                            matching_nodes.append({
                                "id": node_id,
                                "type": entity,
                                "properties": data,
                                "graph_metadata": {
                                    "in_degree": in_degree,
                                    "out_degree": out_degree
                                }
                            })
                            if len(matching_nodes) >= limit:
                                break
                except (ValueError, FileNotFoundError):
                    continue
        result = {
            "criteria": search_criteria,
            "entity_type": entity_type_filter,
            "count": len(matching_nodes),
            "nodes": matching_nodes
        }
        response = create_collection_response("graph_nodes", matching_nodes, {
            "query": {"href": url_for('execute_graph_query')}
        })
        return jsonify(response), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in search_graph_nodes: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
@app.route('/api/v1/graph/shortest-path', methods=['POST'])
def find_shortest_path() -> Tuple[Response, int]:
    try:
        if config['rserv_graph'] == 'disabled':
            raise RServError("Graph functionality is disabled", status_code=400)
        data = request.json
        start_node = data.get('start_node_id')
        end_node = data.get('end_node_id')
        max_depth = data.get('max_depth', config['max_query_depth'])
        if not start_node or not end_node:
            raise RServError("Both start_node_id and end_node_id are required", status_code=400)
        if not isinstance(max_depth, int) or max_depth < 1:
            raise RServError("max_depth must be a positive integer", status_code=400)
        if max_depth > config['max_query_depth']:
            max_depth = config['max_query_depth']
        with LockWithTimeout(graph_lock, "graph_lock"):
            queue = deque([(start_node, [start_node])])
            visited = {start_node}
            while queue:
                current_node, path = queue.popleft()
                if len(path) - 1 > max_depth:
                    continue
                if current_node == end_node:
                    path_details = []
                    for i in range(len(path) - 1):
                        from_node = path[i]
                        to_node = path[i + 1]
                        relationship = graph.get(from_node, {}).get(to_node, "unknown")
                        from_parts = from_node.split(':', 1)
                        to_parts = to_node.split(':', 1)
                        from_info = {"id": from_node}
                        to_info = {"id": to_node}
                        if len(from_parts) == 2:
                            try:
                                from_data = get_entity_data(from_parts[0], int(from_parts[1]))
                                from_info = {
                                    "id": from_node,
                                    "type": from_parts[0],
                                    "properties": from_data
                                }
                            except:
                                pass
                        if len(to_parts) == 2:
                            try:
                                to_data = get_entity_data(to_parts[0], int(to_parts[1]))
                                to_info = {
                                    "id": to_node,
                                    "type": to_parts[0],
                                    "properties": to_data
                                }
                            except:
                                pass
                        path_details.append({
                            "from": from_info,
                            "to": to_info,
                            "relationship": relationship
                        })
                    result = {
                        "start": start_node,
                        "end": end_node,
                        "length": len(path) - 1,
                        "path": path,
                        "edges": path_details
                    }
                    response = create_resource_response("shortest_path", result)
                    return jsonify(response), 200
                if current_node in graph:
                    for neighbor in graph[current_node]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append((neighbor, path + [neighbor]))
        raise RServError(f"No path found between {start_node} and {end_node}", status_code=404)
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in find_shortest_path: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
@app.route('/api/v1/graph/path-exists', methods=['POST'])
def check_path_exists() -> Tuple[Response, int]:
    try:
        if config['rserv_graph'] == 'disabled':
            raise RServError("Graph functionality is disabled", status_code=400)
        data = request.json
        start_node = data.get('start_node_id')
        end_node = data.get('end_node_id')
        max_depth = data.get('max_depth', config['max_query_depth'])
        if not start_node or not end_node:
            raise RServError("Both start_node_id and end_node_id required", status_code=400)
        with LockWithTimeout(graph_lock, "graph_lock"):
            if start_node in graph and end_node in graph[start_node]:
                return jsonify({
                    "exists": True,
                    "reachable_at_depth": 1
                }), 200
        with LockWithTimeout(graph_lock, "graph_lock"):
            visited = {start_node}
            queue = deque([(start_node, 0)])
            while queue:
                current, depth = queue.popleft()
                if depth >= max_depth:
                    continue
                if current in graph:
                    for neighbor in graph[current]:
                        if neighbor == end_node:
                            return jsonify({
                                "exists": True,
                                "reachable_at_depth": depth + 1
                            }), 200
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append((neighbor, depth + 1))
        return jsonify({
            "exists": False,
            "reachable_at_depth": None
        }), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in check_path_exists: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
@app.route('/api/v1/graph/common-neighbors', methods=['POST'])
def find_common_neighbors() -> Tuple[Response, int]:
    try:
        if config['rserv_graph'] == 'disabled':
            raise RServError("Graph functionality is disabled", status_code=400)
        data = request.json
        node1 = data.get('node1_id')
        node2 = data.get('node2_id')
        direction = data.get('direction', 'out')
        if not node1 or not node2:
            raise RServError("Both node1_id and node2_id are required", status_code=400)
        if direction not in ['in', 'out', 'both']:
            raise RServError("Invalid direction. Use: in, out, both", status_code=400)
        common_neighbors = []
        with LockWithTimeout(graph_lock, "graph_lock"):
            if direction in ['out', 'both']:
                neighbors1_out = set(graph.get(node1, {}).keys())
                neighbors2_out = set(graph.get(node2, {}).keys())
                common_out = neighbors1_out & neighbors2_out
                for neighbor in common_out:
                    rel1 = graph[node1][neighbor]
                    rel2 = graph[node2][neighbor]
                    neighbor_parts = neighbor.split(':', 1)
                    neighbor_info = {"id": neighbor}
                    if len(neighbor_parts) == 2:
                        try:
                            neighbor_data = get_entity_data(neighbor_parts[0], int(neighbor_parts[1]))
                            neighbor_info = {
                                "id": neighbor,
                                "type": neighbor_parts[0],
                                "properties": neighbor_data
                            }
                        except:
                            pass
                    common_neighbors.append({
                        "node": neighbor_info,
                        "direction": "out",
                        "relationship_from_node1": rel1,
                        "relationship_from_node2": rel2
                    })
            if direction in ['in', 'both']:
                neighbors1_in = set()
                neighbors2_in = set()
                for source, targets in graph.items():
                    if node1 in targets:
                        neighbors1_in.add(source)
                    if node2 in targets:
                        neighbors2_in.add(source)
                common_in = neighbors1_in & neighbors2_in
                for neighbor in common_in:
                    rel1 = graph[neighbor][node1]
                    rel2 = graph[neighbor][node2]
                    neighbor_parts = neighbor.split(':', 1)
                    neighbor_info = {"id": neighbor}
                    if len(neighbor_parts) == 2:
                        try:
                            neighbor_data = get_entity_data(neighbor_parts[0], int(neighbor_parts[1]))
                            neighbor_info = {
                                "id": neighbor,
                                "type": neighbor_parts[0],
                                "properties": neighbor_data
                            }
                        except:
                            pass
                    common_neighbors.append({
                        "node": neighbor_info,
                        "direction": "in",
                        "relationship_to_node1": rel1,
                        "relationship_to_node2": rel2
                    })
        result = {
            "node1": node1,
            "node2": node2,
            "direction": direction,
            "common_neighbor_count": len(common_neighbors),
            "common_neighbors": common_neighbors
        }
        response = create_resource_response("common_neighbors", result)
        return jsonify(response), 200
    except RServError as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in find_common_neighbors: {str(e)}")
        raise RServError("An unexpected error occurred", status_code=500)
def update_graph_index(entity: str, id: int, data: Dict[str, Any], operation: str) -> None:
    global index
    with LockWithTimeout(index_lock, "index_lock"):
        node_id = f"{entity}:{id}"
        if operation == 'create' or operation == 'update':
            index[data.get('type', entity)].add(node_id)
            for key, value in data.items():
                if isinstance(value, dict) and value.get('type') == 'REF':
                    index[value['entity']].add(node_id)
                    index[f"relationship:{key}"].add(node_id)
        elif operation == 'delete':
            if data:
                index[data.get('type', entity)].discard(node_id)
                for key, value in data.items():
                    if isinstance(value, dict) and value.get('type') == 'REF':
                        index[value['entity']].discard(node_id)
                        index[f"relationship:{key}"].discard(node_id)
def save_graph_index(index_file: str) -> None:
    temp_file = None
    try:
        temp_file = f"{index_file}.tmp"
        with LockWithTimeout(index_lock, "index_lock"):
            index_dict = {k: list(v) for k, v in index.items()}
            with open(temp_file, 'w') as f:
                json.dump(index_dict, f)
            os.rename(temp_file, index_file)
    except Exception as e:
        logger.error(f"Error saving graph index: {str(e)}")
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
def load_graph_index(index_file: str) -> None:
    global index
    if os.path.exists(index_file):
        try:
            with open(index_file, 'r') as f:
                loaded_index = json.load(f)
            with LockWithTimeout(index_lock, "index_lock"):
                index.clear()
                for k, v in loaded_index.items():
                    index[k] = set(v)
        except Exception as e:
            logger.error(f"Error loading graph index: {str(e)}")
            with LockWithTimeout(index_lock, "index_lock"):
                index.clear()
def save_graph_to_file(file_path: str) -> None:
    temp_file = None
    try:
        temp_file = f"{file_path}.tmp"
        with LockWithTimeout(graph_lock, "graph_lock"):
            with open(temp_file, 'w') as f:
                for node_id, neighbors in graph.items():
                    neighbor_list = ' '.join([f"{n}:{t}" for n, t in neighbors.items()])
                    f.write(f"{node_id}:{neighbor_list}\n")
            os.rename(temp_file, file_path)
    except Exception as e:
        logger.error(f"Error saving graph to file: {str(e)}")
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
def load_graph_from_file(file_path: str) -> Dict[str, Dict[str, Any]]:
    global graph
    loaded_graph = defaultdict(dict)
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    parts = line.strip().split(':', 1)
                    if len(parts) == 2:
                        node_id = parts[0]
                        if parts[1]:
                            neighbors = parts[1].split()
                            for neighbor in neighbors:
                                if ':' in neighbor:
                                    n, t = neighbor.split(':', 1)
                                    loaded_graph[node_id][n] = t
        except Exception as e:
            logger.error(f"Error loading graph from file: {str(e)}")
    with LockWithTimeout(graph_lock, "graph_lock"):
        graph.clear()
        graph.update(loaded_graph)
    return dict(loaded_graph)
if __name__ == '__main__':
    print(f"//////////////////////////// rserv {RSERV_VERSION} /////////////////////////////")
    print("----------------------------------------------------------------------")
    print("Server Configuration:")
    print(f"  Host: {config['host']}")
    print(f"  Port: {config['port']}")
    print(f"  Schema: {config['schema_name']}")
    print("\nGraph Configuration:")
    print(f"  Mode: {'Enabled' if config['rserv_graph'] != 'disabled' else 'Disabled'}")
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
    schema_path = os.path.join(BASE_DIR, config['schema_name'])
    if os.path.exists(schema_path) and (config['fulltext_enabled'] or config['rserv_graph'] != 'disabled'):
        for entity in os.listdir(schema_path):
            entity_dir = get_entity_dir(entity)
            if os.path.isdir(entity_dir):
                for filename in os.listdir(entity_dir):
                    if filename.endswith('.json') and not filename.endswith('_next_id.json'):
                        try:
                            with open(os.path.join(entity_dir, filename), 'r') as f:
                                data = json.load(f)
                                if config['rserv_graph'] == 'indexed':
                                    with LockWithTimeout(graph_lock, "graph_lock"):
                                        with LockWithTimeout(index_lock, "index_lock"):
                                            update_graph_index(entity, data.get('id'), data, 'create')
                                            update_graph(entity, data.get('id'), data)
                                            if config['fulltext_enabled']:
                                                with LockWithTimeout(fulltext_lock, "fulltext_lock"):
                                                    index_document(entity, data.get('id'), data)
                                else:
                                    if config['fulltext_enabled']:
                                        with LockWithTimeout(fulltext_lock, "fulltext_lock"):
                                            index_document(entity, data.get('id'), data)
                        except Exception as e:
                            logger.error(f"Error processing file {filename}: {str(e)}")
    if config['rserv_graph'] == 'indexed':
        with LockWithTimeout(graph_lock, "graph_lock"):
            with LockWithTimeout(index_lock, "index_lock"):
                load_graph_index(config['adjacency_index_file'])
                load_graph_from_file(config['adjacency_list_file'])
        logger.info("Running startup graph integrity check...")
        try:
            cleanup_orphaned_graph_nodes()
            logger.info("Startup graph cleanup complete")
        except Exception as e:
            logger.warning(f"Startup graph cleanup failed: {e}")
    initialization_complete.set()
    logger.info("Initialization complete, ready to serve requests")
    start_periodic_cleanup()
    critical_components = [
        ('graph_lock', graph_lock),
        ('index_lock', index_lock),
        ('fulltext_lock', fulltext_lock),
        ('query_lock', query_lock),
        ('cache_lock', cache_lock),
        ('LockWithTimeout', LockWithTimeout),
        ('RServError', RServError)
    ]
    logger.info("Validating critical components...")
    for name, component in critical_components:
        if component is None:
            logger.error(f"CRITICAL: {name} is not defined!")
            sys.exit(1)
    logger.info("All critical components validated ✓")
    app.run(host=config['host'], port=config['port'], debug=config.get('debug', False))