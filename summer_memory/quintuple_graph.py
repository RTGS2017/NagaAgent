import json as _json

try:
    from py2neo import Graph, Node, Relationship
    from py2neo.errors import ServiceUnavailable
except ImportError:
    Graph = None  # type: ignore[assignment,misc]
    Node = None  # type: ignore[assignment,misc]
    Relationship = None  # type: ignore[assignment,misc]
    ServiceUnavailable = Exception  # type: ignore[assignment,misc]

import logging
import sys
import os
from charset_normalizer import from_path
from typing import Optional

# 添加项目根目录到路径，以便导入config
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# 延迟加载的graph实例
_graph: Optional[Graph] = None
_graph_connection_failed: bool = False  # 连接失败标志，避免重复尝试

# Neo4j配置变量（全局）
NEO4J_URI: Optional[str] = None
NEO4J_USER: Optional[str] = None
NEO4J_PASSWORD: Optional[str] = None
NEO4J_DATABASE: Optional[str] = None
GRAG_ENABLED: bool = False


def _load_config():
    """加载Neo4j配置"""
    global NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE, GRAG_ENABLED

    if NEO4J_URI is not None:
        return  # 已经加载过配置

    try:
        from system.config import config
        GRAG_ENABLED = config.grag.enabled
        NEO4J_URI = config.grag.neo4j_uri
        NEO4J_USER = config.grag.neo4j_user
        NEO4J_PASSWORD = config.grag.neo4j_password
        NEO4J_DATABASE = config.grag.neo4j_database
        print(f"[GRAG] 成功从config模块读取配置: enabled={GRAG_ENABLED}, uri={NEO4J_URI}")
        print(f"[GRAG] 全局变量设置后: NEO4J_URI={NEO4J_URI}")
        return  # 成功加载，直接返回
    except Exception as e:
        print(f"[GRAG] 无法从config模块读取Neo4j配置: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        # 兼容旧版本，从config.json读取
        try:
            CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')

            # 使用Charset Normalizer自动检测编码
            charset_results = from_path(CONFIG_PATH)
            if charset_results:
                best_match = charset_results.best()
                if best_match:
                    detected_encoding = best_match.encoding
                    print(f"[GRAG] 检测到配置文件编码: {detected_encoding}")

                    # 使用检测到的编码直接打开文件，然后使用JSON读取
                    with open(CONFIG_PATH, 'r', encoding=detected_encoding) as f:
                        _cfg = _json.load(f)
                else:
                    print("[GRAG] 无法检测配置文件编码，使用回退方法")
                    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                        _cfg = _json.load(f)
            else:
                print("[GRAG] 无法检测配置文件编码，使用回退方法")
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    _cfg = _json.load(f)

            grag_cfg = _cfg.get('grag', {})
            NEO4J_URI = grag_cfg.get('neo4j_uri')
            NEO4J_USER = grag_cfg.get('neo4j_user')
            NEO4J_PASSWORD = grag_cfg.get('neo4j_password')
            NEO4J_DATABASE = grag_cfg.get('neo4j_database')
            GRAG_ENABLED = grag_cfg.get('enabled', True)
        except Exception as e2:
            print(f"[GRAG] 无法从 config.json 读取Neo4j配置: {e2}", file=sys.stderr)
            GRAG_ENABLED = False


def get_graph():
    """获取graph实例（延迟加载）"""
    global _graph, GRAG_ENABLED, _graph_connection_failed

    # 已经连接失败过，不再重试
    if _graph_connection_failed:
        return None

    if _graph is None:
        if Graph is None:
            GRAG_ENABLED = False
            _graph_connection_failed = True
            return None
        # 直接从系统配置获取，避免全局变量问题
        try:
            from system.config import config
            grag_enabled = config.grag.enabled
            neo4j_uri = config.grag.neo4j_uri
            neo4j_user = config.grag.neo4j_user
            neo4j_password = config.grag.neo4j_password
            neo4j_database = config.grag.neo4j_database

            if grag_enabled and neo4j_uri and neo4j_user and neo4j_password:
                try:
                    _graph = Graph(neo4j_uri, auth=(neo4j_user, neo4j_password), name=neo4j_database, timeout=5)
                    _graph.service.kernel_version
                    print("[GRAG] 成功连接到 Neo4j。")
                    GRAG_ENABLED = True
                except ServiceUnavailable:
                    print("[GRAG] 未能连接到 Neo4j，图数据库功能已禁用。请检查 Neo4j 是否正在运行以及配置是否正确。", file=sys.stderr)
                    _graph = None
                    GRAG_ENABLED = False
                    _graph_connection_failed = True
                except Exception as e:
                    print(f"[GRAG] Neo4j连接失败: {e}", file=sys.stderr)
                    _graph = None
                    GRAG_ENABLED = False
                    _graph_connection_failed = True
            else:
                print(f"[GRAG] GRAG未启用或配置不完整: enabled={grag_enabled}, uri={neo4j_uri}")
                GRAG_ENABLED = False
                _graph_connection_failed = True
        except Exception as e:
            print(f"[GRAG] 无法加载配置: {e}", file=sys.stderr)
            GRAG_ENABLED = False
            _graph_connection_failed = True

    return _graph


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

        # 获取graph实例（延迟加载）
        _graph = get_graph()

        # 同步更新Neo4j图谱数据库（仅在graph可用时）
        success = True
        if _graph is not None:
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
                    _graph.merge(h_node, "Entity", "name")
                    _graph.merge(t_node, "Entity", "name")
                    _graph.merge(r)
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
    _graph = get_graph()
    if _graph is not None:
        for kw in keywords:
            query = f"""
            MATCH (e1:Entity)-[r]->(e2:Entity)
            WHERE e1.name CONTAINS '{kw}' OR e2.name CONTAINS '{kw}' OR type(r) CONTAINS '{kw}'
               OR e1.entity_type CONTAINS '{kw}' OR e2.entity_type CONTAINS '{kw}'
            RETURN e1.name, e1.entity_type, type(r), e2.name, e2.entity_type
            LIMIT 5
            """
            res = _graph.run(query).data()
            for record in res:
                results.append((
                    record['e1.name'],
                    record['e1.entity_type'],
                    record['type(r)'],
                    record['e2.name'],
                    record['e2.entity_type']
                ))
    return results