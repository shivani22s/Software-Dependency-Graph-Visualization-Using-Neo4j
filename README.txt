# Software Dependency Graph Visualization Using Neo4j

This project implements an automated software dependency analysis system for Python projects.  
It parses source code using Python's Abstract Syntax Tree (AST), extracts structural relationships
such as imports, function definitions, and function-to-function calls, and stores them in a Neo4j
graph database for interactive visualization.

---

## Features

- Scans all `.py` files in a given project folder
- Extracts:
  - File-level dependencies (imports)
  - Function definitions
  - Function-to-function call relationships
- Builds a graph model with:
  - `File` nodes
  - `Function` nodes
  - `DEPENDS_ON` (file → file) relationships
  - `CONTAINS` (file → function) relationships
  - `CALLS` (function → function) relationships
- Loads the graph into Neo4j
- Visualizes software architecture using Cypher queries

---

## Technologies Used

- **Python 3**
- **AST (Abstract Syntax Tree) module**
- **Neo4j Graph Database**
- **Neo4j Python Driver**
- **Cypher Query Language**

---

## Dataset

The main dataset used for evaluation is the **`requests-main`** source code:

- 36 Python files
- 705 extracted function nodes
- 1837 function-to-function `CALLS` relationships
- 72 file-level `DEPENDS_ON` relationships

The tool can be applied to any other Python project by changing the `--project-path` argument.

---

## Project Structure

```text
dependency-analysis-neo4j/
├── dependency_analyzer_advanced.py   # Main analyzer script (AST + Neo4j)
├── dependency_analyzer.py            # Basic version (optional)
├── requirements.txt                  # Python dependencies (neo4j driver, etc.)
├── sample_project/                   # Small demo project (optional)
│   ├── main.py
│   ├── utils.py
│   └── helper.py
├── screenshots/                      # Neo4j visualization outputs
│   ├── file_graph.png
│   ├── function_graph.png
│   ├── call_graph.png
│   └── combined_graph.png
└── report/
    └── Final_Project_Report.pdf
