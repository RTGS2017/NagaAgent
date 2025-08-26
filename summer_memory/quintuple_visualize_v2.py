from pyvis.network import Network
import webbrowser
import json
import os
import logging

logger = logging.getLogger(__name__)

def load_quintuples_from_json():
    """
    直接从JSON文件中读取五元组数据，解耦数据库依赖
    支持新的增强五元组格式（字典）和旧格式（元组）
    """
    try:
        json_file = "logs/knowledge_graph/quintuples.json"
        print(f"尝试读取 {json_file} 文件...")
        if not os.path.exists(json_file):
            print(f"错误：{json_file} 文件不存在！")
            return set()
            
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f"JSON文件读取成功，包含 {len(data)} 条记录")
            
            # 检查数据格式
            if not data:
                return set()
                
            # 判断是新的字典格式还是旧的元组格式
            if isinstance(data[0], dict):
                # 新格式：增强五元组字典
                result = set()
                for item in data:
                    # 转换为传统元组格式用于可视化
                    quintuple_tuple = (
                        item.get("subject", ""),
                        item.get("subject_type", ""),
                        item.get("predicate", ""),
                        item.get("object", ""),
                        item.get("object_type", "")
                    )
                    result.add(quintuple_tuple)
                print(f"转换新格式为元组后包含 {len(result)} 条唯一记录")
                return result
            else:
                # 旧格式：直接是元组列表
                result = set(tuple(t) for t in data)
                print(f"旧格式直接转换后包含 {len(result)} 条唯一记录")
                return result
    except FileNotFoundError:
        print("错误：找不到 quintuples.json 文件")
        return set()
    except json.JSONDecodeError as e:
        print(f"错误：JSON文件格式错误 - {e}")
        return set()
    except Exception as e:
        print(f"错误：读取文件时发生异常 - {e}")
        return set()

def visualize_quintuples():
    """
    直接从JSON文件中读取所有五元组，并生成可视化图谱 graph.html
    解耦版本：不依赖Neo4j数据库，直接从JSON文件读取数据
    """
    try:
        print("开始读取五元组数据...")
        quintuples = load_quintuples_from_json()
        print(f"读取到 {len(quintuples)} 条原始数据")
        
        if not quintuples:
            logger.warning("从JSON文件中未获取到任何五元组，无法生成可视化图谱")
            print("未获取到任何五元组，无法生成图谱。")
            return
        
        logger.info(f"从JSON文件获取到 {len(quintuples)} 条五元组进行可视化")

        # 过滤非法五元组
        print("开始过滤无效五元组...")
        valid_quintuples = [
            t for t in quintuples
            if isinstance(t, tuple) and len(t) == 5 and all(isinstance(x, str) and x.strip() for x in t)
        ]
        print(f"过滤后剩余 {len(valid_quintuples)} 条有效五元组")
        
        if not valid_quintuples:
            print("错误：没有有效的五元组数据！")
            return
        
        print("开始创建网络图...")
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
        
        print("开始构建图谱节点和边...")
        edge_count = 0
        for head, head_type, rel, tail, tail_type in valid_quintuples:
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
            edge_count += 1

        print(f"图谱构建完成：{len(added_nodes)} 个节点，{edge_count} 条边")
        print("正在生成HTML文件...")
        # 确保目录存在
        import os
        os.makedirs("logs/knowledge_graph", exist_ok=True)
        
        html_file = "logs/knowledge_graph/graph.html"
        net.write_html(html_file)
        print(f"HTML文件生成完成：{html_file}")

        try:
            print("尝试打开浏览器...")
            # 获取正确的绝对路径
            abs_html_path = os.path.abspath(html_file)
            webbrowser.open("file:///" + abs_html_path)
            print("浏览器打开成功！")
        except Exception as e:
            print(f"无法自动打开浏览器：{e}")

        print("知识图谱已生成：graph.html，请手动打开查看。")
        logger.info("知识图谱可视化完成，文件 graph.html 已生成")

    except Exception as e:
        print(f"发生异常：{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        logger.error(f"可视化五元组失败: {e}")
        print(f"生成知识图谱失败: {e}")


# 添加主函数用于测试
if __name__ == "__main__":
    print("=" * 50)
    print("开始测试可视化功能")
    print("=" * 50)
    visualize_quintuples()