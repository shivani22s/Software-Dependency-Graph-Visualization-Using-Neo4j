import os
import ast
from neo4j import GraphDatabase
import argparse

# ==========================
# CONFIG – CHANGE THESE
# ==========================
NEO4J_URI = "bolt://localhost:7687"  # Default local Neo4j
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Ruhiee@2233"  # <-- YOUR PASSWORD HERE


# ---------- AST VISITOR FOR FUNCTIONS & CALLS ----------

class FunctionCallVisitor(ast.NodeVisitor):
    """
    Visits a Python AST, collects:
      - function definitions (name, lineno)
      - function calls (caller_name, caller_lineno, called_simple_name)
      Also captures calls at module (global) level.
    """
    def __init__(self):
        self.functions = []  # list of (func_name, lineno)
        self.calls = []      # list of (caller_name, caller_lineno, called_name)
        self._current_func = None  # ast node
        self._current_func_name = None
        self._current_func_lineno = None

    def visit_FunctionDef(self, node):
        prev_func = self._current_func
        prev_name = self._current_func_name
        prev_lineno = self._current_func_lineno

        self._current_func = node
        self._current_func_name = node.name
        self._current_func_lineno = node.lineno

        self.functions.append((node.name, node.lineno))
        self.generic_visit(node)

        self._current_func = prev_func
        self._current_func_name = prev_name
        self._current_func_lineno = prev_lineno

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_Call(self, node):
        # Who is the caller?
        if self._current_func_name is not None:
            caller_name = self._current_func_name
            caller_lineno = self._current_func_lineno
        else:
            # Call at module/global level
            caller_name = "__module__"
            caller_lineno = 0

        # Who is being called (simple name)?
        called_name = None
        target = node.func

        # foo()
        if isinstance(target, ast.Name):
            called_name = target.id
        # obj.foo()
        elif isinstance(target, ast.Attribute):
            called_name = target.attr

        if called_name:
            self.calls.append((caller_name, caller_lineno, called_name))

        self.generic_visit(node)


# ---------- ANALYZER: FILES, IMPORTS, FUNCTIONS, CALLS ----------

class DependencyAnalyzerAdvanced:
    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)

        # File-level
        self.file_nodes = {}          # rel_path -> module_name
        self.module_to_files = {}     # module_name -> [rel_paths]
        self.file_dependencies = []   # list of (from_file, to_file)

        # Function-level
        self.function_nodes = {}      # func_id -> {"path", "name", "lineno"}
        self.funcname_to_ids = {}     # simple func name -> [func_id]
        self.contains_edges = []      # (file_path, func_id)
        self.call_edges = []          # (caller_func_id, callee_func_id)

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

    def analyze_files(self):
        print("[+] Parsing files for imports, functions, and calls...")

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

            # --- IMPORTS -> FILE DEPENDENCIES ---
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
                            self.file_dependencies.append((rel_path, target_file))

            # --- FUNCTIONS & CALLS ---
            visitor = FunctionCallVisitor()
            visitor.visit(tree)

            # Create a pseudo "module" function node to represent top-level code
            module_func_id = f"{rel_path}:__module__:0"
            self.function_nodes[module_func_id] = {
                "path": rel_path,
                "name": "__module__",
                "lineno": 0,
            }
            self.contains_edges.append((rel_path, module_func_id))
            self.funcname_to_ids.setdefault("__module__", []).append(module_func_id)

            # Real function definitions in this file
            local_func_map = {}  # (name, lineno) -> func_id

            for func_name, lineno in visitor.functions:
                func_id = f"{rel_path}:{func_name}:{lineno}"
                self.function_nodes[func_id] = {
                    "path": rel_path,
                    "name": func_name,
                    "lineno": lineno,
                }
                local_func_map[(func_name, lineno)] = func_id
                self.contains_edges.append((rel_path, func_id))
                self.funcname_to_ids.setdefault(func_name, []).append(func_id)

            # Map calls to function IDs (best-effort)
            for caller_name, caller_lineno, called_simple in visitor.calls:
                if caller_name == "__module__":
                    caller_id = module_func_id
                else:
                    caller_key = (caller_name, caller_lineno)
                    caller_id = local_func_map.get(caller_key)

                if not caller_id:
                    continue  # could not resolve caller

                candidate_callees = self.funcname_to_ids.get(called_simple, [])
                for callee_id in candidate_callees:
                    self.call_edges.append((caller_id, callee_id))

        print(f"[+] Extracted {len(self.file_dependencies)} file dependencies.")
        print(f"[+] Found {len(self.function_nodes)} function-like nodes (incl. module).")
        print(f"[+] Mapped {len(self.call_edges)} function calls.")


# ---------- NEO4J LOADER ----------

class Neo4jLoaderAdvanced:
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

    def create_file_dependencies(self, file_deps):
        print("[+] Creating DEPENDS_ON relationships (file-level)...")
        with self.driver.session() as session:
            for from_path, to_path in file_deps:
                session.run(
                    """
                    MATCH (a:File {path: $from_path})
                    MATCH (b:File {path: $to_path})
                    MERGE (a)-[:DEPENDS_ON]->(b)
                    """,
                    from_path=from_path,
                    to_path=to_path,
                )

    def create_function_nodes(self, function_nodes):
        print("[+] Creating Function nodes in Neo4j...")
        with self.driver.session() as session:
            for func_id, data in function_nodes.items():
                session.run(
                    """
                    MERGE (fn:Function {id: $id})
                    SET fn.name = $name,
                        fn.path = $path,
                        fn.lineno = $lineno
                    """,
                    id=func_id,
                    name=data["name"],
                    path=data["path"],
                    lineno=data["lineno"],
                )

    def create_contains_edges(self, contains_edges):
        print("[+] Creating CONTAINS relationships (File -> Function)...")
        with self.driver.session() as session:
            for file_path, func_id in contains_edges:
                session.run(
                    """
                    MATCH (f:File {path: $path})
                    MATCH (fn:Function {id: $id})
                    MERGE (f)-[:CONTAINS]->(fn)
                    """,
                    path=file_path,
                    id=func_id,
                )

    def create_call_edges(self, call_edges):
        print("[+] Creating CALLS relationships (Function -> Function)...")
        with self.driver.session() as session:
            for caller_id, callee_id in call_edges:
                session.run(
                    """
                    MATCH (c:Function {id: $caller_id})
                    MATCH (d:Function {id: $callee_id})
                    MERGE (c)-[:CALLS]->(d)
                    """,
                    caller_id=caller_id,
                    callee_id=callee_id,
                )


# ---------- MAIN ----------

def main():
    parser = argparse.ArgumentParser(
        description="Advanced Dependency Analysis (File + Function level) using Neo4j"
    )
    parser.add_argument(
        "--project-path",
        type=str,
        required=True,
        help="Path to the root folder of the Python project",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the Neo4j database before loading",
    )
    args = parser.parse_args()

    analyzer = DependencyAnalyzerAdvanced(args.project_path)
    analyzer.scan_project_files()
    analyzer.analyze_files()

    loader = Neo4jLoaderAdvanced(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    if args.clear:
        loader.clear_database()

    loader.create_file_nodes(analyzer.file_nodes.keys())
    loader.create_file_dependencies(analyzer.file_dependencies)
    loader.create_function_nodes(analyzer.function_nodes)
    loader.create_contains_edges(analyzer.contains_edges)
    loader.create_call_edges(analyzer.call_edges)

    loader.close()

    print("\n[+] Done!")
    print("Now open Neo4j Browser and try for FILES:")
    print("  MATCH (f:File)-[r:DEPENDS_ON]->(g:File) RETURN f,r,g;")
    print("For FUNCTIONS (structure):")
    print("  MATCH (f:File)-[:CONTAINS]->(fn:Function) RETURN f, fn LIMIT 100;")
    print("For FUNCTION CALLS:")
    print("  MATCH (fn:Function)-[c:CALLS]->(callee:Function) RETURN fn, c, callee LIMIT 100;")


if __name__ == "__main__":
    main()
