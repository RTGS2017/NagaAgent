from pyvis.network import Network
import webbrowser
from .quintuple_graph import get_all_quintuples
import logging

logger = logging.getLogger(__name__)

def visualize_quintuples():
    """
    直接从 Neo4j 数据库中读取所有五元组，并生成可视化图谱 graph.html
    """
    try:
        quintuples = get_all_quintuples()
        if not quintuples:
            logger.warning("从数据库中未获取到任何五元组，无法生成可视化图谱")
            print("未获取到任何五元组，无法生成图谱。")
            return
        
        logger.info(f"从数据库获取到 {len(quintuples)} 条五元组进行可视化")

        # 过滤非法五元组
        quintuples = [
            t for t in quintuples
            if isinstance(t, tuple) and len(t) == 5 and all(isinstance(x, str) and x.strip() for x in t)
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
        # 定义不同实体类型的颜色
        type_colors = {
            '人物': '#FF6B6B',
            '地点': '#4ECDC4', 
            '组织': '#45B7D1',
            '物品': '#96CEB4',
            '概念': '#FFEAA7',
            '时间': '#DDA0DD',
            '事件': '#F4A460',
            '活动': '#FFB347'
        }
        default_color = '#CCCCCC'
        
        for head, head_type, rel, tail, tail_type in quintuples:
            # 添加主体节点
            if head not in added_nodes:
                head_color = type_colors.get(head_type, default_color)
                net.add_node(head, label=f"{head}\n({head_type})", color=head_color, font={'size': 20})
                added_nodes.add(head)
            
            # 添加客体节点
            if tail not in added_nodes:
                tail_color = type_colors.get(tail_type, default_color)
                net.add_node(tail, label=f"{tail}\n({tail_type})", color=tail_color, font={'size': 20})
                added_nodes.add(tail)
            
            # 添加关系边
            net.add_edge(head, tail, label=rel, length=120, font={'size': 18})

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
        logger.error(f"可视化五元组失败: {e}")
        print(f"生成知识图谱失败: {e}")