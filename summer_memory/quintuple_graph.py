import json as _json
from py2neo import Graph, Node, Relationship
from py2neo.errors import ServiceUnavailable
import logging
import sys
import os

# 添加项目根目录到路径，以便导入config
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# 从config模块读取Neo4j配置
try:
    from system.config import config
    GRAG_ENABLED = config.grag.enabled
    NEO4J_URI = config.grag.neo4j_uri
    NEO4J_USER = config.grag.neo4j_user
    NEO4J_PASSWORD = config.grag.neo4j_password
    NEO4J_DATABASE = config.grag.neo4j_database
    
    try:
        if GRAG_ENABLED:
            graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), name=NEO4J_DATABASE)
            try:
                graph.service.kernel_version
                print("[GRAG] 成功连接到 Neo4j。")
            except ServiceUnavailable:
                print("[GRAG] 未能连接到 Neo4j，图数据库功能已临时禁用。请检查 Neo4j 是否正在运行以及配置是否正确。", file=sys.stderr)
                graph = None
                GRAG_ENABLED = False
        else:
            graph = None
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
            if GRAG_ENABLED:
                graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), name=NEO4J_DATABASE)
                try:
                    graph.service.kernel_version
                    print("[GRAG] 成功连接到 Neo4j。")
                except ServiceUnavailable:
                    print("[GRAG] 未能连接到 Neo4j，图数据库功能已临时禁用。请检查 Neo4j 是否正在运行以及配置是否正确。", file=sys.stderr)
                    graph = None
                    GRAG_ENABLED = False
            else:
                graph = None
        except Exception as e:
            print(f"[GRAG] Neo4j连接失败: {e}", file=sys.stderr)
            graph = None
            GRAG_ENABLED = False
    except Exception as e:
        print(f"[GRAG] 无法从 config.json 读取Neo4j配置: {e}", file=sys.stderr)
        graph = None
        GRAG_ENABLED = False

logger = logging.getLogger(__name__)
QUINTUPLES_FILE = "logs/knowledge_graph/quintuples.json"  # 修改为logs目录下的专门文件夹


def load_quintuples():
    try:
        with open(QUINTUPLES_FILE, 'r', encoding='utf-8') as f:
            return set(tuple(t) for t in _json.load(f))
    except FileNotFoundError:
        return set()


def save_quintuples(quintuples):
    # 确保目录存在
    import os
    os.makedirs(os.path.dirname(QUINTUPLES_FILE), exist_ok=True)
    
    with open(QUINTUPLES_FILE, 'w', encoding='utf-8') as f:
        _json.dump(list(quintuples), f, ensure_ascii=False, indent=2)


def store_quintuples(new_quintuples) -> bool:
    """存储五元组到文件和Neo4j，返回是否成功"""
    try:
        all_quintuples = load_quintuples()
        all_quintuples.update(new_quintuples)  # 集合自动去重

        # 持久化到文件
        save_quintuples(all_quintuples)

        # 同步更新Neo4j图谱数据库（仅在GRAG_ENABLED时）
        success = True
        if graph is not None:
            success_count = 0
            for head, head_type, rel, tail, tail_type in new_quintuples:
                if not head or not tail:
                    logger.warning(f"跳过无效五元组，head或tail为空: {(head, head_type, rel, tail, tail_type)}")
                    continue

                try:
                    # 创建带类型的节点
                    h_node = Node("Entity", name=head, entity_type=head_type)
                    t_node = Node("Entity", name=tail, entity_type=tail_type)

                    # 创建关系，保存主体和客体类型信息
                    r = Relationship(h_node, rel, t_node, head_type=head_type, tail_type=tail_type)

                    # 合并节点时使用name和entity_type作为唯一标识
                    graph.merge(h_node, "Entity", "name")
                    graph.merge(t_node, "Entity", "name")
                    graph.merge(r)
                    success_count += 1
                except Exception as e:
                    logger.error(f"存储五元组失败: {head}-{rel}-{tail}, 错误: {e}")
                    success = False

            logger.info(f"成功存储 {success_count}/{len(new_quintuples)} 个五元组到Neo4j")
            # 如果至少成功存储了一个五元组，就认为是成功的
            if success_count > 0:
                return True
            else:
                return False
        else:
            logger.info(f"跳过Neo4j存储（未启用），保存 {len(new_quintuples)} 个五元组到文件")
            return True  # 文件存储成功也算成功
    except Exception as e:
        logger.error(f"存储五元组失败: {e}")
        return False

def get_all_quintuples():
    return load_quintuples()


def query_graph_by_keywords(keywords):
    results = []
    if graph is not None:
        for kw in keywords:
            query = f"""
            MATCH (e1:Entity)-[r]->(e2:Entity)
            WHERE e1.name CONTAINS '{kw}' OR e2.name CONTAINS '{kw}' OR type(r) CONTAINS '{kw}'
               OR e1.entity_type CONTAINS '{kw}' OR e2.entity_type CONTAINS '{kw}'
            RETURN e1.name, e1.entity_type, type(r), e2.name, e2.entity_type
            LIMIT 5
            """
            res = graph.run(query).data()
            for record in res:
                results.append((
                    record['e1.name'], 
                    record['e1.entity_type'],
                    record['type(r)'], 
                    record['e2.name'],
                    record['e2.entity_type']
                ))
    return results