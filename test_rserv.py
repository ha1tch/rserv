import unittest
import os
import json
from rserv import *

class TestRServSupportFunctions(unittest.TestCase):

    def test_get_entity_dir(self):
        self.assertEqual(get_entity_dir("person"), os.path.join(BASE_DIR, "schema", "person"))
        self.assertEqual(get_entity_dir("location"), os.path.join(BASE_DIR, "schema", "location"))

    def test_get_entity_file(self):
        self.assertEqual(get_entity_file("person", 1), os.path.join(BASE_DIR, "schema", "person", "1.json"))
        self.assertEqual(get_entity_file("location", 2), os.path.join(BASE_DIR, "schema", "location", "2.json"))

    def test_load_json_from_file(self):
        file_path = os.path.join(BASE_DIR, "schema", "person", "1.json")
        data = load_json_from_file(file_path)
        self.assertIsInstance(data, dict)
        self.assertTrue("id" in data)
        self.assertTrue("name" in data)

        file_path = os.path.join(BASE_DIR, "schema", "location", "2.json")
        data = load_json_from_file(file_path)
        self.assertIsInstance(data, dict)
        self.assertTrue("id" in data)
        self.assertTrue("name" in data)
        self.assertTrue("address" in data)

    def test_save_json_to_file(self):
        data = {"id": 1, "name": "John Doe"}
        file_path = os.path.join(BASE_DIR, "schema", "person", "1.json")
        save_json_to_file(file_path, data)
        self.assertTrue(os.path.exists(file_path))
        with open(file_path, "r") as f:
            loaded_data = json.load(f)
        self.assertEqual(loaded_data, data)

    def test_validate_entity_name(self):
        self.assertTrue(validate_entity_name("person"))
        self.assertTrue(validate_entity_name("person_1"))
        self.assertTrue(validate_entity_name("person_123"))

        with self.assertRaises(RServError):
            validate_entity_name("person-1")
        with self.assertRaises(RServError):
            validate_entity_name("person.1")
        with self.assertRaises(RServError):
            validate_entity_name("person 1")
        with self.assertRaises(RServError):
            validate_entity_name("person123!")
        with self.assertRaises(RServError):
            validate_entity_name("person-123")

    def test_validate_id(self):
        self.assertTrue(validate_id(1))
        self.assertTrue(validate_id(123))
        self.assertTrue(validate_id(1234567890))

        with self.assertRaises(RServError):
            validate_id(-1)
        with self.assertRaises(RServError):
            validate_id(0)
        with self.assertRaises(RServError):
            validate_id("1")
        with self.assertRaises(RServError):
            validate_id(1.0)

    def test_validate_query(self):
        self.assertTrue(validate_query("MATCH (a) RETURN a"))
        self.assertTrue(validate_query("BFS MATCH (a) RETURN a"))
        self.assertTrue(validate_query("DFS MATCH (a) RETURN a"))
        self.assertTrue(validate_query("MATCH (a)-[:KNOWS]->(b) RETURN a, b"))

        with self.assertRaises(RServError):
            validate_query("MATCH a RETURN a")
        with self.assertRaises(RServError):
            validate_query("MATCH (a) RETURN")
        with self.assertRaises(RServError):
            validate_query("MATCH (a) RETURN b")
        with self.assertRaises(RServError):
            validate_query("MATCH (a)-[:KNOWS] RETURN a")
        with self.assertRaises(RServError):
            validate_query("MATCH (a)-[:KNOWS]-> RETURN a")
        with self.assertRaises(RServError):
            validate_query("MATCH (a)-[:KNOWS]->(b) RETURN a")

    def test_create_collection_response(self):
        data = [{"id": 1, "name": "John Doe"}, {"id": 2, "name": "Jane Doe"}]
        links = {"self": {"href": "/people"}}
        response = create_collection_response("people", data, links)
        self.assertIsInstance(response, dict)
        self.assertEqual(response["data"], data)
        self.assertEqual(response["links"], links)
        self.assertEqual(response["type"], "collection")

    def test_create_resource_response(self):
        data = {"id": 1, "name": "John Doe"}
        links = {"self": {"href": "/people/1"}}
        response = create_resource_response("person", data, links)
        self.assertIsInstance(response, dict)
        self.assertEqual(response["data"], data)
        self.assertEqual(response["links"], links)
        self.assertEqual(response["type"], "resource")

    def test_create_error_response(self):
        response = create_error_response("Invalid request", 400)
        self.assertIsInstance(response, dict)
        self.assertEqual(response["error"], "Invalid request")
        self.assertEqual(response["status"], 400)

    def test_load_graph_from_file(self):
        graph = load_graph_from_file(os.path.join(BASE_DIR, "schema", "graph.txt"))
        self.assertIsInstance(graph, dict)
        self.assertEqual(len(graph), 6)
        self.assertEqual(graph["1"], {'type': 'person', 'neighbors': ['2', '3']})
        self.assertEqual(graph["2"], {'type': 'location', 'neighbors': ['1']})
        self.assertEqual(graph["3"], {'type': 'person', 'neighbors': ['1', '4']})
        self.assertEqual(graph["4"], {'type': 'location', 'neighbors': ['3']})
        self.assertEqual(graph["5"], {'type': 'person', 'neighbors': []})
        self.assertEqual(graph["6"], {'type': 'location', 'neighbors': []})

    def test_load_index_from_file(self):
        index = load_index_from_file(os.path.join(BASE_DIR, "schema", "index.txt"))
        self.assertIsInstance(index, dict)
        self.assertEqual(len(index), 3)
        self.assertEqual(index["person"], {'1', '3'})
        self.assertEqual(index["location"], {'2', '4'})
        self.assertEqual(index["relationship:LIVES_IN"], {'1', '3'})

    def test_build_graph_index(self):
        graph = load_graph_from_file(os.path.join(BASE_DIR, "schema", "graph.txt"))
        build_graph_index(graph)
        self.assertEqual(len(index), 3)
        self.assertEqual(index["person"], {'1', '3', '5'})
        self.assertEqual(index["location"], {'2', '4', '6'})
        self.assertEqual(index["relationship:LIVES_IN"], {'1', '3'})
        self.assertEqual(index["relationship:WORKS_AT"], {'3'})
        self.assertEqual(index["relationship:KNOWS"], {'1', '3'})

    def test_update_graph_index(self):
        graph = load_graph_from_file(os.path.join(BASE_DIR, "schema", "graph.txt"))
        build_graph_index(graph)
        self.assertEqual(len(index), 3)
        self.assertEqual(index["person"], {'1', '3', '5'})
        self.assertEqual(index["location"], {'2', '4', '6'})
        self.assertEqual(index["relationship:LIVES_IN"], {'1', '3'})

        # Add a new relationship
        data = {"id": 1, "type": "person", "neighbors": ['2', '3', '7']}
        update_graph_index("person", 1, data, "update")
        self.assertEqual(len(index), 3)
        self.assertEqual(index["person"], {'1', '3', '5', '7'})
        self.assertEqual(index["location"], {'2', '4', '6'})
        self.assertEqual(index["relationship:LIVES_IN"], {'1', '3'})

        # Remove an existing relationship
        data = {"id": 1, "type": "person", "neighbors": ['2', '3']}
        update_graph_index("person", 1, data, "delete")
        self.assertEqual(len(index), 3)
        self.assertEqual(index["person"], {'3', '5', '7'})
        self.assertEqual(index["location"], {'2', '4', '6'})
        self.assertEqual(index["relationship:LIVES_IN"], {'3'})

    def test_save_graph_index(self):
        index = {"person": {'1', '3', '5'}, "location": {'2', '4', '6'}, "relationship:LIVES_IN": {'1', '3'}}
        index_file = os.path.join(BASE_DIR, "schema", "index.txt")
        save_graph_index(index_file)
        self.assertTrue(os.path.exists(index_file))
        with open(index_file, "r") as f:
            loaded_index = json.load(f)
        self.assertEqual(loaded_index, index)


