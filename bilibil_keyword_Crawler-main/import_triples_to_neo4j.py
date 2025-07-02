import os
import argparse
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "8168377qwe")

def import_file(session, path: str):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().strip("\ufeff")
            if not line or "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            start, relation, end = parts[:3]
            # 在关系上加原始 rel 属性，类型统一 TRIPLE
            query = (
                "MERGE (s:Entity {name: $start}) "
                "MERGE (t:Entity {name: $end}) "
                "MERGE (s)-[r:TRIPLE {rel: $relation}]->(t)"
            )
            session.run(query, start=start, end=end, relation=relation)

def clear_database(session):
    # 清空数据库（可选，谨慎使用！）
    session.run("MATCH (n) DETACH DELETE n")

def import_triples(directory: str, clear_db=False):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    txt_files = [f for f in os.listdir(directory) if f.endswith('.txt')]
    with driver.session() as session:
        if clear_db:
            print("Clearing all nodes and relationships in database...")
            clear_database(session)
        for fname in txt_files:
            path = os.path.join(directory, fname)
            import_file(session, path)
            print(f"Imported {fname}")
    driver.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import triples into Neo4j")
    parser.add_argument(
        "directory", default=os.path.join(os.path.dirname(__file__), "guides", "triples"),
        nargs="?",
        help="Directory containing triple txt files"
    )
    parser.add_argument(
        "--clear", action="store_true",
        help="Clear all nodes and relationships in the database before import"
    )
    args = parser.parse_args()
    if os.path.isdir(args.directory):
        import_triples(args.directory, clear_db=args.clear)
    else:
        print(f"Directory not found: {args.directory}")
