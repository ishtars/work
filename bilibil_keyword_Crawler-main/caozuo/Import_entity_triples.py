import csv
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "8168377qwe"

GAME_NAME = "三角洲行动"
COMPANY_NAME = "腾讯"


def create_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def ensure_base_nodes(tx):
    tx.run("MERGE (:Company {name: $name})", name=COMPANY_NAME)
    tx.run("MERGE (:Game {name: $game})", game=GAME_NAME)


def create_entity_and_relations(tx, entity, canonical=None):
    tx.run("MERGE (e:Entity {name: $name})", name=entity)
    tx.run(
        "MATCH (g:Game {name: $game}) MATCH (e:Entity {name: $name}) MERGE (g)-[:HAS_ENTITY]->(e)",
        game=GAME_NAME,
        name=entity,
    )
    if canonical and canonical != entity:
        tx.run(
            "MATCH (a:Entity {name: $a}) MATCH (b:Entity {name: $b}) MERGE (a)-[:SYNONYM_OF]->(b)",
            a=entity,
            b=canonical,
        )


def import_entities(csv_path):
    driver = create_driver()
    with driver.session() as session:
        session.write_transaction(ensure_base_nodes)
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if not row:
                    continue
                names = [n.strip() for n in row[0].split(',') if n.strip()]
                if not names:
                    continue
                canonical = names[0]
                session.write_transaction(create_entity_and_relations, canonical)
                for name in names[1:]:
                    session.write_transaction(
                        create_entity_and_relations, name, canonical
                    )
    driver.close()


if __name__ == "__main__":
    import_entities("entity_similar_groups.csv")