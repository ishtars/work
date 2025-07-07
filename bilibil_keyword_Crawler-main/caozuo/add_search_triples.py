from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)
import re
from neo4j import GraphDatabase, basic_auth

app = Flask(__name__)
app.secret_key = 'test_secret_key'  # 防止跨站随便设置

# 配置Neo4j连接信息
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "8168377qwe"
driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD)
)

# 查找关系
def search_relations(entity):
    """Find triples where the given entity is either the source or the target."""
    with driver.session() as session:
        query = (
            "MATCH (n)-[r]->(m) "
            "WHERE n.name = $entity OR m.name = $entity "
            "RETURN n.name AS start, r.rel AS relation, m.name AS end"
        )
        result = session.run(query, entity=entity)
        return list(result)

# 列出三元组，支持分页
def list_all_triples(offset: int = 0, limit: int = 50):
    with driver.session() as session:
        query = (
            "MATCH (s)-[r]->(e) "
            "RETURN id(r) AS rid, s.name AS start, r.rel AS relation, e.name AS end "
            "ORDER BY rid SKIP $offset LIMIT $limit"
        )
        result = session.run(query, offset=offset, limit=limit)
        return list(result)

# 根据关系ID删除三元组
def delete_triple_by_id(rid: int):
    with driver.session() as session:
        session.run("MATCH ()-[r]->() WHERE id(r)=$rid DELETE r", rid=rid)

# 更新三元组
def update_triple(rid: int, start: str, relation: str, end: str):
    with driver.session() as session:
        session.run("MATCH ()-[r]->() WHERE id(r)=$rid DELETE r", rid=rid)
        query = (
            "MERGE (n {name: $start}) "
            "MERGE (m {name: $end}) "
            "MERGE (n)-[r:TRIPLE {rel: $relation}]->(m)"
        )
        session.run(query, start=start, end=end, relation=relation)

# 删除实体和相关目标与出边
def delete_entity_and_targets(start_entity):
    with driver.session() as session:
        # 找所有目标节点id
        query_targets = (
            "MATCH (n {name: $start_entity})-[r]->(m) "
            "RETURN id(m) AS mid"
        )
        targets = session.run(query_targets, start_entity=start_entity)
        target_ids = [record['mid'] for record in targets]

        # 先删实体自己（包含出边）
        session.run(
            "MATCH (n {name: $start_entity}) DETACH DELETE n",
            start_entity=start_entity
        )

        # 删目标节点（目标节点若无其他入度）
        for mid in target_ids:
            session.run(
                "MATCH (m) WHERE id(m) = $mid "
                "OPTIONAL MATCH (x)-[rel]->(m) "
                "WITH m, count(rel) AS incoming "
                "WHERE incoming = 0 "
                "DETACH DELETE m",
                mid=mid
            )

# 写入三元组
def write_triple(start_entity, relation, end_entity):
    with driver.session() as session:
        query = (
            "MERGE (n {name: $start_entity}) "
            "MERGE (m {name: $end_entity}) "
            "MERGE (n)-[r:TRIPLE {rel: $relation}]->(m) "
            "RETURN n, r, m"
        )
        session.run(
            query,
            start_entity=start_entity,
            end_entity=end_entity,
            relation=relation,
        )



@app.route('/triples')
def list_triples():
    page = int(request.args.get('page', 1))
    limit = 50
    offset = (page - 1) * limit
    triples = list_all_triples(offset, limit)
    return render_template('triples.html', triples=triples, page=page)


@app.route('/delete/<int:rid>', methods=['POST'])
def delete_triple(rid):
    page = int(request.args.get('page', 1))
    delete_triple_by_id(rid)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(status='ok')
    flash('已删除三元组', 'success')
    return redirect(url_for('list_triples', page=page))


@app.route('/edit/<int:rid>', methods=['GET', 'POST'])
def edit_triple(rid):
    page = int(request.args.get('page', 1))
    if request.method == 'POST':
        s = request.form.get('start', '').strip()
        r = request.form.get('relation', '').strip()
        e = request.form.get('end', '').strip()
        if s and r and e:
            update_triple(rid, s, r, e)
            flash('已更新三元组', 'success')
            return redirect(url_for('list_triples', page=page))
        else:
            flash('请完整填写三元组', 'warning')
    with driver.session() as session:
        q = (
            "MATCH (s)-[r]->(e) WHERE id(r)=$rid "
            "RETURN s.name AS start, r.rel AS relation, e.name AS end"
        )
        res = session.run(q, rid=rid).single()
        triple = res.data() if res else None
    return render_template('edit_triple.html', triple=triple, page=page)

@app.route('/', methods=['GET', 'POST'])
def index():
    search_results = None
    # 查询表单
    if request.method == 'POST' and "search_btn" in request.form:
        search_entity = request.form.get('search_entity', '').strip()
        if search_entity:
            search_results = search_relations(search_entity)
            if not search_results:
                flash('未查到相关关系。', 'info')

    # 写入三元组表单
    if request.method == 'POST' and 'insert_btn' in request.form:
        s = request.form.get('triple_start', '').strip()
        r = request.form.get('triple_rel', '').strip()
        e = request.form.get('triple_end', '').strip()
        if s and r and e:
            write_triple(s, r, e)
            flash(f"已写入三元组: ({s})-[:{r}]->({e})", 'success')
        else:
            flash('请完整填写三元组的三个输入栏。', 'warning')
        return redirect(url_for('index'))

    # 批量写入表单
    if request.method == 'POST' and 'bulk_insert_btn' in request.form:
        raw_text = request.form.get('bulk_triples', '').strip()
        if raw_text:
            lines = [l for l in raw_text.splitlines() if l.strip()]
            for line in lines:
                parts = [p.strip() for p in re.split('[—-]', line) if p.strip()]
                if len(parts) == 3:
                    write_triple(parts[0], parts[1], parts[2])
            flash(f'已批量写入 {len(lines)} 个三元组', 'success')
        else:
            flash('请输入要批量写入的三元组，每行一个。', 'warning')
        return redirect(url_for('index'))

    # 删除实体表单
    if request.method == 'POST' and 'del_btn' in request.form:
        del_entity = request.form.get('del_entity', '').strip()
        if del_entity:
            delete_entity_and_targets(del_entity)
            flash(f"已删除实体“{del_entity}”及其所有出发关系和目标节点（如独立）。", 'success')
        else:
            flash("请填写要删除的实体名。", 'warning')
        return redirect(url_for('index'))

    return render_template('index.html', search_results=search_results)

if __name__ == '__main__':
    app.run(debug=True)