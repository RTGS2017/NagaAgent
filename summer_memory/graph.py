import json as _json
from py2neo import Graph, Node, Relationship
import logging
import sys
import os

# 添加项目根目录到路径，以便导入config
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# 从config模块读取Neo4j配置
try:
    from config import config
    GRAG_ENABLED = config.grag.enabled
    NEO4J_URI = config.grag.neo4j_uri
    NEO4J_USER = config.grag.neo4j_user
    NEO4J_PASSWORD = config.grag.neo4j_password
    NEO4J_DATABASE = config.grag.neo4j_database
    
    try:
        graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), name=NEO4J_DATABASE) if GRAG_ENABLED else None
    except Exception as e:
        print(f"[GRAG] Neo4j连接失败: {e}", file=sys.stderr)
        graph = None
        GRAG_ENABLED = False
except Exception as e:
    print(f"[GRAG] 无法从config模块读取Neo4j配置: {e}", file=sys.stderr)
    # 兼容旧版本，从config.json读取
    try:
        CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            _cfg = _json.load(f)
        grag_cfg = _cfg.get('grag', {})
        NEO4J_URI = grag_cfg['neo4j_uri']
        NEO4J_USER = grag_cfg['neo4j_user']
        NEO4J_PASSWORD = grag_cfg['neo4j_password']
        NEO4J_DATABASE = grag_cfg['neo4j_database']
        GRAG_ENABLED = grag_cfg.get('enabled', True)
        try:
            graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), name=NEO4J_DATABASE) if GRAG_ENABLED else None
        except Exception as e:
            print(f"[GRAG] Neo4j连接失败: {e}", file=sys.stderr)
            graph = None
            GRAG_ENABLED = False
    except Exception as e:
        print(f"[GRAG] 无法从 config.json 读取Neo4j配置: {e}", file=sys.stderr)
        graph = None
        GRAG_ENABLED = False

logger = logging.getLogger(__name__)
TRIPLES_FILE = "triples.json"


def load_triples():
    try:
        with open(TRIPLES_FILE, 'r', encoding='utf-8') as f:
            return set(tuple(t) for t in _json.load(f))
    except FileNotFoundError:
        return set()


def save_triples(triples):
    with open(TRIPLES_FILE, 'w', encoding='utf-8') as f:
        _json.dump(list(triples), f, ensure_ascii=False, indent=2)


def store_triples(new_triples) -> bool:
    """存储三元组到文件和Neo4j，返回是否成功"""
    try:
        # 1. 保存到本地文件
        all_triples = load_triples()
        all_triples.update(new_triples)
        save_triples(all_triples)

        # 2. 存储到Neo4j（如果启用）
        if graph is not None:
            success_count = 0
            for head, rel, tail in new_triples:
                if not head or not tail:
                    logger.warning(f"跳过无效三元组，head或tail为空: {(head, rel, tail)}")
                    continue

                try:
                    h_node = Node("Entity", name=head)
                    t_node = Node("Entity", name=tail)
                    r = Relationship(h_node, rel, t_node)

                    graph.merge(h_node, "Entity", "name")
                    graph.merge(t_node, "Entity", "name")
                    graph.merge(r)
                    success_count += 1
                except Exception as e:
                    logger.error(f"存储三元组失败: {head}-{rel}-{tail}, 错误: {e}")

            logger.info(f"成功存储 {success_count}/{len(new_triples)} 个三元组到Neo4j")
            return success_count > 0  # 只要有成功存储的就返回True
        else:
            logger.info(f"跳过Neo4j存储（未启用），保存 {len(new_triples)} 个三元组到文件")
            return True  # 文件存储成功也算成功
    except Exception as e:
        logger.error(f"存储三元组失败: {e}")
        return False


def get_all_triples():
    return load_triples()


def query_graph_by_keywords(keywords):
    results = []
    if graph is not None:
        for kw in keywords:
            query = f"""
            MATCH (e1:Entity)-[r]->(e2:Entity)
            WHERE e1.name CONTAINS '{kw}' OR e2.name CONTAINS '{kw}' OR type(r) CONTAINS '{kw}'
            RETURN e1.name, type(r), e2.name
            LIMIT 5
            """
            res = graph.run(query).data()
            for record in res:
                results.append((record['e1.name'], record['type(r)'], record['e2.name']))
    return results
