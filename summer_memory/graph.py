import json as _json
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

class Graph:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def check_connection(self):
        """Verifies the connection to the database and returns True if successful."""
        try:
            self.driver.verify_connectivity()
            return True
        except (ServiceUnavailable, AuthError):
            return False

    def close(self):
