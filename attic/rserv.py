"""
rserv: A simple REST prototyping server

Copyright 2024 Haitch

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Author: Haitch <haitch@duck.com>
Repository: https://github.com/ha1tch/rserv

This script implements a lightweight REST API server for rapid prototyping
and development. It provides CRUD operations, pagination, sorting, and
basic search functionality for JSON documents.
"""

import os
import json
import time
import argparse
import fcntl
import logging
import subprocess
import sys
from functools import cmp_to_key
from datetime import datetime

# Version constant
VERSION = "0.2.1"

# Check and install required dependencies
required_packages = ['flask', 'python-dotenv']
installed_packages = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze']).decode('utf-8').split('\n')
installed_packages = [package.split('==')[0].lower() for package in installed_packages if package]

for package in required_packages:
    if package.lower() not in installed_packages:
        print(f"Installing required package: {package}")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Set up logging with custom timestamp format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'  # Custom date format
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BASE_DIR = 'data'
SCHEMA_DIR = 'schema'
DEFAULT_SCHEMA = 'default'
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(SCHEMA_DIR, exist_ok=True)

# Default configuration
DEFAULT_CONFIG = {
    'patch_null': 'store',
    'host': '0.0.0.0',
    'port': 9090,
    'cache_ttl': 300,
    'default_page_size': 10,
    'schema_name': DEFAULT_SCHEMA,
    'cascading_delete': False
}

# Simple in-memory cache
cache = {}

def print_startup_notice():
    notice = f"""
%%%%   %%%%%%%       %%%%%%%       %%%%%%%%    %%%%  %%%%%%%%%%%         %%%%
%´´´%%%´´´´´´´%    %%´´´´´´´%    %%´´´´´´´´%%  %´´´%%´´´´´´%:´´´%       %´´´% 
%´´´´´´´´´´´´´´% %%´´´´´´´´´´%  %´´´´%%%%´´´´%%%´´´´´´´´´´´% %´´´%     %´´´% 
%%´´´´´%%%%´´´´´%%´´´´´%%%´´´´%%´´´´%    %´´´´%%%´´´´%%%´´´´% %´´´:   :´´´% 
 %´´´´%    %´´´´% %´´´´% %%%%% %´´´´´%%%%´´´´´% %´´´%   %´´´% %´´´%   %´´´%   
 %´´´´%    %%%%%%   %´´´´%     %´´´´´´´´´´´´´%  %´´´%   %%%%%  %´´´% %´´´%   
 %´´´´%               %´´´´´,  %´´´´%%%%%%%%%   %´´´%           %´´´%´´´%    
 %´´´´%          %%%%%  %´´´´% %´´´´´%          %´´´%           %´´´´´´´%     
 %´´´´%          %´´´´%%%´´´´´%%´´´´´´%         %´´´%            %´´´´´%      
 %´´´´%          %´´´´´´´´´´´%  %´´´´´´%%%%%%   %´´´%             :´´´:      
 %´´´´%           %´´´´´´´´´%    %%´´´´´´´´´%   %´´´%              %´%       
 %%%%%%            %%%%%%%%%       %%%%%%%%%%   %%%%%               %  
                                                      
////////////// rserv {VERSION} // a simple REST prototyping server //////////////
-----------------------------------------------------------------------------
    """
    print(notice)

def parse_arguments():
    parser = argparse.ArgumentParser(description='Entity Management System')
    parser.add_argument('--config', help='Path to the configuration file')
    parser.add_argument('--patch-null', choices=['store', 'delete'],
                        help='Specify how to handle null values in PATCH requests')
    parser.add_argument('--host', help='Host to run the server on')
    parser.add_argument('--port', type=int, help='Port to run the server on')
    parser.add_argument('--cache-ttl', type=int, help='Cache Time To Live in seconds')
    parser.add_argument('--page-size', type=int, help='Default page size for pagination')
    parser.add_argument('--schema', help='Specify which schema to use')
    parser.add_argument('--list-schemas', action='store_true', help='List available schemas')
    parser.add_argument('--cascading-delete', action='store_true',
                        help='Enable cascading deletes for referential integrity')
    return parser.parse_args()

def load_config_file(config_file_path=None):
    if config_file_path and os.path.exists(config_file_path):
        # Load the specified configuration file
        load_dotenv(config_file_path, override=True)
        logger.info(f"Loaded configuration from: {config_file_path}")
    else:
        # Check for fallback configuration files in order
        fallback_files = ['.env', '.rserv.conf', 'rserv.conf']
        for file in fallback_files:
            if os.path.exists(file):
                load_dotenv(file, override=True)
                logger.info(f"Loaded configuration from: {file}")
                break
        else:
            logger.info("No configuration file found. Using default values.")

def get_config():
    args = parse_arguments()
    
    # Load configuration file
    load_config_file(args.config)
    
    # Start with default configuration
    config = DEFAULT_CONFIG.copy()

    # Update with environment variables (including those from config file)
    config['patch_null'] = os.getenv('PATCH_NULL', config['patch_null'])
    config['host'] = os.getenv('HOST', config['host'])
    config['port'] = int(os.getenv('PORT', config['port']))
    config['cache_ttl'] = int(os.getenv('CACHE_TTL', config['cache_ttl']))
    config['default_page_size'] = int(os.getenv('DEFAULT_PAGE_SIZE', config['default_page_size']))
    config['schema_name'] = os.getenv('SCHEMA', config['schema_name'])
    config['cascading_delete'] = os.getenv('CASCADING_DELETE', '').lower() == 'true'

    # Update config with command line arguments (if provided)
    if args.patch_null:
        config['patch_null'] = args.patch_null
    if args.host:
        config['host'] = args.host
    if args.port:
        config['port'] = args.port
    if args.cache_ttl:
        config['cache_ttl'] = args.cache_ttl
    if args.page_size:
        config['default_page_size'] = args.page_size
    if args.schema:
        config['schema_name'] = args.schema
    if args.cascading_delete:
        config['cascading_delete'] = True
    
    # Add the list_schemas option
    config['list_schemas'] = args.list_schemas

    return config

def get_entity_dir(entity):
    entity_dir = os.path.join(BASE_DIR, config['schema_name'], entity)
    os.makedirs(entity_dir, exist_ok=True)
    return entity_dir

def get_entity_file(entity, id):
    # Sanitize entity and id to prevent path traversal
    safe_entity = ''.join(c for c in entity if c.isalnum() or c in ('_', '-'))
    safe_id = str(id).replace('/', '').replace('\\', '')
    return os.path.join(get_entity_dir(safe_entity), f"{safe_id}.json")

def get_next_id(entity):
    entity_dir = get_entity_dir(entity)
    id_file = os.path.join(entity_dir, '_next_id.txt')
    
    with open(id_file, 'a+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)  # Exclusive lock
        try:
            f.seek(0)
            content = f.read().strip()
            if content:
                next_id = int(content) + 1
            else:
                next_id = 1
            f.seek(0)
            f.truncate()
            f.write(str(next_id))
            return next_id
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)  # Release the lock

def get_pagination_params():
    page = max(1, request.args.get('page', 1, type=int))
    per_page = max(1, min(100, request.args.get('per_page', config['default_page_size'], type=int)))
    return page, per_page

def get_sorting_params():
    sort_params = request.args.get('sort', 'id:asc')
    return [param.split(':') for param in sort_params.split(',')]

def type_aware_compare(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return (a > b) - (a < b)
    elif isinstance(a, str) and isinstance(b, str):
        return (a.lower() > b.lower()) - (a.lower() < b.lower())
    else:
        # Handle mixed types by converting to strings
        return (str(a) > str(b)) - (str(a) < str(b))

def multi_field_comparator(sort_fields):
    def compare(a, b):
        for field, order in sort_fields:
            a_val = a.get(field)
            b_val = b.get(field)
            comp = type_aware_compare(a_val, b_val)
            if comp != 0:
                return comp if order == 'asc' else -comp
        return 0
    return compare

def sort_entities(entities, sort_params):
    comparator = multi_field_comparator(sort_params)
    return sorted(entities, key=cmp_to_key(comparator))

def paginate_results(results, page, per_page):
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

def load_entity(file_path):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON from file: {file_path}. Error: {str(e)}")
        raise ValueError(f"Invalid JSON in file: {file_path}")
    except IOError as e:
        logger.error(f"Failed to read file: {file_path}. Error: {str(e)}")
        raise IOError(f"Failed to read file: {file_path}")

def field_matches(entity_value, query_value):
    if isinstance(entity_value, str) and isinstance(query_value, str):
        return query_value.lower() in entity_value.lower()
    elif isinstance(entity_value, (int, float)) and isinstance(query_value, (int, float)):
        return entity_value == query_value
    elif isinstance(entity_value, (int, float)) and isinstance(query_value, str):
        try:
            return entity_value == float(query_value)
        except ValueError:
            return False
    return False

def get_all_entities(entity, filter_func=None):
    entity_dir = get_entity_dir(entity)
    entities = []
    for filename in os.listdir(entity_dir):
        if filename.endswith('.json'):
            file_path = os.path.join(entity_dir, filename)
            try:
                data = load_entity(file_path)
                if data and (filter_func is None or filter_func(data)):
                    entities.append(data)
            except (ValueError, IOError) as e:
                logger.error(f"Error loading entity from {file_path}: {str(e)}")
    return entities

def get_cached_result(cache_key):
    if cache_key in cache:
        result, timestamp = cache[cache_key]
        if time.time() - timestamp < config['cache_ttl']:
            return result
    return None

def set_cached_result(cache_key, result):
    cache[cache_key] = (result, time.time())

def handle_null_values(data):
    if config['patch_null'] == 'delete':
        return {k: v for k, v in data.items() if v is not None}
    return data  # 'store' behavior: keep null values

def cascade_delete(entity, id):
    deleted_docs = []
    for dependent_entity, schema in schemas.items():
        for field, rules in schema.items():
            if "foreign_key" in rules and rules["foreign_key"]["entity"] == entity:
                dependent_dir = os.path.join(BASE_DIR, config['schema_name'], dependent_entity)
                for filename in os.listdir(dependent_dir):
                    if filename.endswith('.json'):
                        file_path = os.path.join(dependent_dir, filename)
                        try:
                            with open(file_path, 'r') as f:
                                data = json.load(f)
                            if data.get(field) == id:
                                os.remove(file_path)
                                deleted_docs.append(f"{dependent_entity}/{data['id']}")
                                # Recursively delete documents that depend on this one
                                deleted_docs.extend(cascade_delete(dependent_entity, data['id']))
                        except (json.JSONDecodeError, IOError) as e:
                            logger.error(f"Error processing file {file_path}: {str(e)}")
    return deleted_docs

# Integrated schema loading functions
def load_schemas(schema_name, base_dir=SCHEMA_DIR):
    schema_dir = os.path.join(base_dir, schema_name)
    schemas = {}
    
    if not os.path.exists(schema_dir):
        if schema_name == DEFAULT_SCHEMA:
            logger.info("No 'default' schema found. Running in schema-less mode.")
        else:
            logger.warning(f"Schema directory {schema_dir} does not exist.")
        return schemas

    for filename in os.listdir(schema_dir):
        if filename.endswith('.json'):
            entity_name = os.path.splitext(filename)[0]
            file_path = os.path.join(schema_dir, filename)
            try:
                with open(file_path, 'r') as f:
                    schema = json.load(f)
                schemas[entity_name] = schema
                logger.info(f"Loaded schema for entity {entity_name}")
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON in {file_path}. Skipping this file.")
            except Exception as e:
                logger.error(f"Error reading {file_path}: {str(e)}")

    if schema_name == DEFAULT_SCHEMA and schemas:
        logger.info("'default' schema found and loaded. Schema validation will be enforced.")

    return schemas

def list_available_schemas(base_dir=SCHEMA_DIR):
    if not os.path.exists(base_dir):
        logger.warning(f"Base schema directory {base_dir} does not exist.")
        return []
    
    return [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]

def validate_schema(schema):
    errors = []
    valid_types = {"string", "integer", "float", "boolean", "datetime", "date", "json"}
    
    for field, rules in schema.items():
        if not isinstance(rules, dict):
            errors.append(f"Field '{field}' must have a dictionary of rules")
            continue
        
        if "type" not in rules:
            errors.append(f"Field '{field}' is missing 'type' specification")
        elif rules["type"] not in valid_types:
            errors.append(f"Field '{field}' has invalid type '{rules['type']}'")
        
        if "required" in rules and not isinstance(rules["required"], bool):
            errors.append(f"Field '{field}' 'required' must be a boolean")
        
        if "max_length" in rules and not isinstance(rules["max_length"], int):
            errors.append(f"Field '{field}' 'max_length' must be an integer")
        
        if "foreign_key" in rules:
            if not isinstance(rules["foreign_key"], dict):
                errors.append(f"Field '{field}' 'foreign_key' must be a dictionary")
            elif "entity" not in rules["foreign_key"] or "field" not in rules["foreign_key"]:
                errors.append(f"Field '{field}' 'foreign_key' must specify 'entity' and 'field'")
    
    return len(errors) == 0, errors

def load_and_validate_schemas(schema_name, base_dir=SCHEMA_DIR):
    schemas = load_schemas(schema_name, base_dir)
    validated_schemas = {}
    
    for entity, schema in schemas.items():
        is_valid, errors = validate_schema(schema)
        if is_valid:
            validated_schemas[entity] = schema
            logger.info(f"Schema for entity '{entity}' is valid")
        else:
            logger.error(f"Schema for entity '{entity}' is invalid:")
            for error in errors:
                logger.error(f"  - {error}")
    
    return validated_schemas

class DynamicValidator:
    def __init__(self, schemas, schema_name):
        self.schemas = schemas
        self.schema_name = schema_name

    def validate(self, entity, data):
        if entity not in self.schemas:
            return True, []  # No schema defined, so no validation needed

        schema = self.schemas[entity]
        errors = []

        for field, rules in schema.items():
            if rules.get("required", False) and field not in data:
                errors.append(f"Missing required field: {field}")
            elif field in data:
                value = data[field]
                field_type = rules["type"]

                if field_type == "string":
                    if not isinstance(value, str):
                        errors.append(f"Field {field} must be a string")
                    elif "max_length" in rules and len(value) > rules["max_length"]:
                        errors.append(f"Field {field} exceeds maximum length of {rules['max_length']}")
                elif field_type == "integer":
                    if not isinstance(value, int):
                        errors.append(f"Field {field} must be an integer")
                elif field_type == "float":
                    if not isinstance(value, (int, float)):
                        errors.append(f"Field {field} must be a number")
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

        return len(errors) == 0, errors

@app.route('/api/v1/<entity>', methods=['POST'])
def create_entity(entity):
    data = request.json
    is_valid, errors = validator.validate(entity, data)
    if not is_valid:
        return jsonify({"error": "Validation failed", "details": errors}), 400
    
    new_id = get_next_id(entity)
    data['id'] = new_id
    file_path = get_entity_file(entity, new_id)
    
    with open(file_path, 'w') as f:
        json.dump(data, f)
    logger.info(f"Created resource of entity {entity} with id {new_id}")
    return jsonify({"message": f"New resource of entity {entity} created successfully with id {new_id}", "id": new_id}), 201

@app.route('/api/v1/<entity>/<int:id>', methods=['GET'])
def get_entity(entity, id):
    file_path = get_entity_file(entity, id)
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            data = json.load(f)
        logger.info(f"Retrieved resource of entity {entity} with id {id}")
        return jsonify(data), 200
    else:
        logger.warning(f"Resource of entity {entity} with id {id} not found")
        return jsonify({"error": f"Resource of entity {entity} with id {id} not found"}), 404

@app.route('/api/v1/<entity>/<int:id>', methods=['PUT'])
def update_entity(entity, id):
    file_path = get_entity_file(entity, id)
    if not os.path.exists(file_path):
        logger.warning(f"Attempted to update non-existent resource of entity {entity} with id {id}")
        return jsonify({"error": f"Resource of entity {entity} with id {id} not found"}), 404
    
    data = request.json
    is_valid, errors = validator.validate(entity, data)
    if not is_valid:
        return jsonify({"error": "Validation failed", "details": errors}), 400
    
    data['id'] = id  # Ensure the ID in the data matches the URL
    
    with open(file_path, 'w') as f:
        json.dump(data, f)
    logger.info(f"Updated resource of entity {entity} with id {id}")
    return jsonify({"message": f"Resource of entity {entity} with id {id} updated successfully"}), 200

@app.route('/api/v1/<entity>/<int:id>', methods=['PATCH'])
def patch_entity(entity, id):
    file_path = get_entity_file(entity, id)
    if not os.path.exists(file_path):
        logger.warning(f"Attempted to patch non-existent {entity} with id {id}")
        return jsonify({"error": f"{entity} with id {id} not found"}), 404

    with open(file_path, 'r') as f:
        existing_data = json.load(f)

    patch_data = request.json
    patch_data = handle_null_values(patch_data)

    # Merge patch data with existing data
    merged_data = {**existing_data, **patch_data}
    
    # Validate the merged data
    is_valid, errors = validator.validate(entity, merged_data)
    if not is_valid:
        return jsonify({"error": "Validation failed", "details": errors}), 400

    for key, value in patch_data.items():
        if key != 'id':  # Prevent changing the ID
            if value is None and config['patch_null'] == 'delete':
                existing_data.pop(key, None)
            else:
                existing_data[key] = value

    with open(file_path, 'w') as f:
        json.dump(existing_data, f)

    logger.info(f"Patched {entity} with id {id}")
    return jsonify({
        "message": f"{entity} with id {id} patched successfully",
        "updated_fields": list(patch_data.keys())
    }), 200

@app.route('/api/v1/<entity>/<int:id>', methods=['DELETE'])
def delete_entity(entity, id):
    file_path = get_entity_file(entity, id)
    if not os.path.exists(file_path):
        logger.warning(f"Attempted to delete non-existent {entity} with id {id}")
        return jsonify({"error": f"{entity} with id {id} not found"}), 404
    
    cascaded_deletes = []
    if config['cascading_delete']:
        cascaded_deletes = cascade_delete(entity, id)
    
    os.remove(file_path)
    logger.info(f"Deleted {entity} with id {id}")
    
    response = {"message": f"{entity} with id {id} deleted successfully"}
    if cascaded_deletes:
        response["cascaded_deletes"] = cascaded_deletes
    
    return jsonify(response), 200

@app.route('/api/v1/<entity>/list', methods=['GET'])
def list_entities(entity):
    page, per_page = get_pagination_params()
    sort_params = get_sorting_params()
    
    cache_key = f"{entity}:list:{sort_params}:{page}:{per_page}"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        logger.info(f"Retrieved cached list for {entity}")
        return jsonify(cached_result), 200

    all_entities = get_all_entities(entity)
    sorted_entities = sort_entities(all_entities, sort_params)
    paginated_results = paginate_results(sorted_entities, page, per_page)
    paginated_results['sort'] = ','.join([f"{field}:{order}" for field, order in sort_params])

    set_cached_result(cache_key, paginated_results)
    logger.info(f"Listed {entity} (page {page}, {per_page} per page)")
    return jsonify(paginated_results), 200

@app.route('/api/v1/<entity>/search', methods=['GET'])
def search_entities(entity):
    query = request.args.get('query', '').strip()
    field = request.args.get('field', 'name').strip()
    page, per_page = get_pagination_params()
    sort_params = get_sorting_params()

    if not query:
        logger.warning(f"Search attempted for {entity} without a query")
        return jsonify({"error": "Query parameter is required"}), 400

    cache_key = f"{entity}:search:{query}:{field}:{sort_params}:{page}:{per_page}"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        logger.info(f"Retrieved cached search results for {entity}")
        return jsonify(cached_result), 200

    def search_filter(data):
        return field in data and field_matches(data[field], query)

    matching_entities = get_all_entities(entity, search_filter)
    sorted_entities = sort_entities(matching_entities, sort_params)
    paginated_results = paginate_results(sorted_entities, page, per_page)
    paginated_results['search_field'] = field
    paginated_results['sort'] = ','.join([f"{field}:{order}" for field, order in sort_params])

    set_cached_result(cache_key, paginated_results)
    logger.info(f"Searched {entity} for '{query}' in field '{field}' (page {page}, {per_page} per page)")
    return jsonify(paginated_results), 200

@app.route('/api/v1/<entity>/save/<int:id>', methods=['POST'])
def save_entity(entity, id):
    file_path = get_entity_file(entity, id)
    
    if os.path.exists(file_path):
        logger.warning(f"Attempted to save existing {entity} with id {id}")
        return jsonify({
            "error": f"{entity} with id {id} already exists. Use PUT /api/v1/{entity}/{id} to update."
        }), 409  # 409 Conflict
    
    data = request.json
    is_valid, errors = validator.validate(entity, data)
    if not is_valid:
        return jsonify({"error": "Validation failed", "details": errors}), 400
    
    data['id'] = id
    
    with open(file_path, 'w') as f:
        json.dump(data, f)
    
    logger.info(f"Saved new {entity} with id {id}")
    return jsonify({"message": f"{entity} with id {id} created successfully"}), 201



if __name__ == '__main__':
    print_startup_notice()
    config = get_config()

    if config['list_schemas']:
        available_schemas = list_available_schemas()
        if available_schemas:
            print("Available schemas:")
            for schema in available_schemas:
                print(f"  - {schema}")
        else:
            print("No schemas available.")
        sys.exit(0)

    print(f"Server configuration:")
    print(f"  Host: {config['host']}")
    print(f"  Port: {config['port']}")
    print(f"  PATCH null handling: {config['patch_null']}")
    print(f"  Cache TTL: {config['cache_ttl']} seconds")
    print(f"  Default page size: {config['default_page_size']}")
    print(f"  Schema: {config['schema_name']} {'(default)' if config['schema_name'] == DEFAULT_SCHEMA else ''}")
    print(f"  Cascading Delete: {'Enabled' if config['cascading_delete'] else 'Disabled'}")
    
    schemas = load_and_validate_schemas(config['schema_name'])
    if not schemas:
        if config['schema_name'] == DEFAULT_SCHEMA:
            print(f"No 'default' schema found. Running in schema-less mode. Data will be stored in ./data/default/")
        else:
            print(f"Warning: No valid schema files found for '{config['schema_name']}'. Running without schema validation.")
    else:
        if config['schema_name'] == DEFAULT_SCHEMA:
            print(f"'default' schema found. Schema validation will be enforced for data in ./data/default/")
        print(f"Loaded and validated schemas for {len(schemas)} entities")
    
    # Ensure the data directory for this schema exists
    os.makedirs(os.path.join(BASE_DIR, config['schema_name']), exist_ok=True)
    
    validator = DynamicValidator(schemas, config['schema_name'])
       
    logger.info(f"Starting rserv {VERSION} on {config['host']}:{config['port']} with schema '{config['schema_name']}'")
    app.run(host=config['host'], port=config['port'])
