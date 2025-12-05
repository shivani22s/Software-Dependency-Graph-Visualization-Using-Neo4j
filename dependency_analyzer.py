import os
import ast
from neo4j import GraphDatabase
import argparse

# ==========================
# CONFIG – CHANGE THESE
# ==========================
NEO4J_URI = "bolt://localhost:7687"  # Default local Neo4j
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Ruhiee@2233"  # <- CHANGE THIS


class DependencyAnalyzer:
    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.file_nodes = {}  # path -> module_name
        self.module_to_files = {}  # module_name -> [paths]

    def scan_project_files(self):
        print(f"[+] Scanning project: {self.project_root}")
        for root, _, files in os.walk(self.project_root):
            for f in files:
                if f.endswith(".py"):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, self.project_root)
                    module_name = os.path.splitext(os.path.basename(f))[0]

                    self.file_nodes[rel_path] = module_name
                    self.module_to_files.setdefault(module_name, []).append(rel_path)

        print(f"[+] Found {len(self.file_nodes)} Python files.")

    def extract_dependencies(self):
        dependencies = []
        print("[+] Extracting imports...")

        for rel_path in self.file_nodes.keys():
            abs_path = os.path.join(self.project_root, rel_path)

            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    source = f.read()
            except Exception as e:
                print(f"[!] Could not read {rel_path}: {e}")
                continue

            try:
                tree = ast.parse(source)
            except SyntaxError as e:
                print(f"[!] Syntax error in {rel_path}: {e}")
                continue

            imported_modules = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_modules.add(alias.name.split(".")[0])

                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported_modules.add(node.module.split(".")[0])

            for mod in imported_modules:
                if mod in self.module_to_files:
                    for target_file in self.module_to_files[mod]:
                        if target_file != rel_path:
                            dependencies.append((rel_path, target_file))

        print(f"[+] Extracted {len(dependencies)} dependencies.")
        return dependencies


class Neo4jLoader:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def clear_database(self):
        print("[!] Clearing existing nodes and relationships in Neo4j...")
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def create_file_nodes(self, file_paths):
        print("[+] Creating File nodes in Neo4j...")
        with self.driver.session() as session:
            for path in file_paths:
                session.run(
                    """
                    MERGE (f:File {path: $path})
                    SET f.name = $name
                    """,
                    path=path,
                    name=os.path.basename(path),
                )

    def create_dependencies(self, dependencies):
        print("[+] Creating DEPENDS_ON relationships in Neo4j...")
        with self.driver.session() as session:
            for from_path, to_path in dependencies:
                session.run(
                    """
                    MATCH (a:File {path: $from_path})
                    MATCH (b:File {path: $to_path})
                    MERGE (a)-[:DEPENDS_ON]->(b)
                    """,
                    from_path=from_path,
                    to_path=to_path,
                )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-path", type=str, required=True)
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    analyzer = DependencyAnalyzer(args.project_path)
    analyzer.scan_project_files()
    deps = analyzer.extract_dependencies()

    loader = Neo4jLoader(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    if args.clear:
        loader.clear_database()

    loader.create_file_nodes(analyzer.file_nodes.keys())
    loader.create_dependencies(deps)
    loader.close()

    print("\n[+] Done!")
    print("Open Neo4j Browser and try:")
    print("MATCH (f:File) RETURN f;")
    print("MATCH (a:File)-[r:DEPENDS_ON]->(b:File) RETURN a, r, b;")


if __name__ == "__main__":
    main()
