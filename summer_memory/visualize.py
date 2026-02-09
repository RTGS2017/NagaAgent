from pyvis.network import Network
import webbrowser
from .graph import get_all_triples
import logging

logger = logging.getLogger(__name__)

def visualize_triples():
    """
    直接从 Neo4j 数据库中读取所有三元组，并生成可视化图谱 graph.html
    """
    try:
        triples = get_all_triples()
        if not triples:
            logger.warning("从数据库中未获取到任何三元组，无法生成可视化图谱")
            print("未获取到任何三元组，无法生成图谱。")
            return
        
        logger.info(f"从数据库获取到 {len(triples)} 条三元组进行可视化")

        # 过滤非法三元组
        triples = [
            t for t in triples
            if isinstance(t, tuple) and len(t) == 3 and all(isinstance(x, str) and x.strip() for x in t)
        ]
        
        net = Network(height='1600px', width='100%', notebook=False)
        net.use_template = False
        net.barnes_hut()
        net.set_options("""
        var options = {
          "physics": {
            "barnesHut": {
              "gravitationalConstant": -8000,
              "springLength": 100,
              "springConstant": 0.04
            },
            "minVelocity": 0.75
          }
        }
        """)

        added_nodes = set()
        for head, rel, tail in triples:
            for node, color in [(head, '#FFAA00'), (tail, '#00AAFF')]:
                if node not in added_nodes:
                    net.add_node(node, label=node, color=color, font={'size': 24})
                    added_nodes.add(node)
            net.add_edge(head, tail, label=rel, length=120, font={'size': 20})

        net.write_html("graph.html")

        try:
            # 获取正确的绝对路径
            abs_html_path = os.path.abspath("graph.html")
            webbrowser.open("file:///" + abs_html_path)
        except Exception as e:
            print(f"无法自动打开浏览器：{e}")

        print("知识图谱已生成：graph.html，请手动打开查看。")
        logger.info("知识图谱可视化完成，文件 graph.html 已生成")

    except Exception as e:
        logger.error(f"可视化三元组失败: {e}")
        print(f"生成知识图谱失败: {e}")
