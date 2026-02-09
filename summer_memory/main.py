import os
import sys
import subprocess
import atexit
import logging
import traceback
import webbrowser

from .quintuple_extractor import extract_quintuples
from .quintuple_graph import store_quintuples
from .quintuple_rag_query import query_knowledge, set_context

# 添加上级目录以导入 config.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from system.config import GRAG_NEO4J_USER, GRAG_NEO4J_PASSWORD, GRAG_NEO4J_DATABASE

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# --- Docker 控制逻辑 ---
def generate_docker_compose(template_path="docker-compose.template.yml", output_path="docker-compose.yml"):
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
        auth = f"{GRAG_NEO4J_USER}/{GRAG_NEO4J_PASSWORD}"
        content = template.replace("${NEO4J_AUTH}", auth).replace("${NEO4J_DB}", GRAG_NEO4J_DATABASE)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("已根据 config.py 生成 docker-compose.yml")
    except Exception as e:
        logger.error(f"生成 docker-compose.yml 失败: {e}")
        raise

def is_neo4j_running():
    try:
        output = subprocess.check_output(["docker", "ps", "--filter", "name=rag_neo4j", "--filter", "status=running", "--format", "{{.Names}}"])
        return "rag_neo4j" in output.decode("utf-8")
    except Exception as e:
        logger.error(f"检查容器状态失败: {e}")
        return False

def check_docker_compose_version():
    """检查可用的 Docker Compose 命令版本"""
    if os.system("docker compose version") == 0:
        compose_cmd = ["docker", "compose"]
    elif os.system("docker-compose --version") == 0:
        compose_cmd = ["docker-compose"]
    else:
        logger.error("未找到有效的 Docker Compose命令")
        return None
    return compose_cmd

def start_neo4j_container():
    if is_neo4j_running():
        logger.info("Neo4j 容器已在运行，无需重新启动。")
        return
    try:
        generate_docker_compose()
        logger.info("正在启动 Neo4j Docker 容器...")
        # 检查可用的 docker compose 命令
        compose_cmd = check_docker_compose_version()
        if not compose_cmd:
            raise Exception("未找到有效的 Docker Compose 命令")
        
        subprocess.run(compose_cmd + ["up", "-d"], check=True)
        logger.info("Neo4j 容器已启动。")
    except subprocess.CalledProcessError:
        logger.error("启动 Neo4j 容器失败，请检查 Docker 配置")
        raise


def stop_neo4j_container():
    try:
        logger.info("正在关闭 Neo4j Docker 容器...")
        # 检查可用的 docker compose 命令
        compose_cmd = check_docker_compose_version()
        if not compose_cmd:
            raise Exception("未找到有效的 Docker Compose 命令")
            
        subprocess.run(compose_cmd + ["down"], check=True)
        logger.info("Neo4j 容器已关闭。")
    except subprocess.CalledProcessError:
        logger.warning("Neo4j 容器关闭失败")


atexit.register(stop_neo4j_container)


# --- 核心业务逻辑 ---
def batch_add_texts(texts):# 批量处理文本，提取五元组并存储
    try:
        all_quintuples = set()
        for text in texts:
            if not text:
                logger.warning("跳过空文本")
                continue
            logger.info(f"处理文本: {text[:50]}...")
            quintuples = extract_quintuples(text)
            if not quintuples:
                logger.warning(f"文本未提取到五元组: {text}")
            else:
                logger.info(f"提取到五元组: {quintuples}")
            all_quintuples.update(quintuples)

        if not all_quintuples:
            logger.warning("未提取到任何五元组")
            return False

        valid_quintuples = [
            t for t in all_quintuples if len(t) == 5 and all(isinstance(x, str) and x.strip() for x in t)
        ]

        if len(valid_quintuples) < len(all_quintuples):
            logger.warning(f"过滤掉 {len(all_quintuples) - len(valid_quintuples)} 个无效五元组")

        if not valid_quintuples:
            logger.warning("无有效五元组")
            return False

        store_quintuples(valid_quintuples)
        set_context(texts)# 设置查询上下文
        return True
    except Exception as e:
        logger.error(f"处理文本失败: {e}")
        return False


def batch_add_from_file(filename):# 从文件批量处理文本
    try:
        if not os.path.exists(filename):
            logger.error(f"文件 {filename} 不存在")
            raise FileNotFoundError(f"文件 {filename} 不存在")
        with open(filename, 'r', encoding='utf-8') as f:
            texts = [line.strip() for line in f if line.strip()]
        if not texts:
            logger.warning(f"文件 {filename} 为空")
            return False
        logger.info(f"读取文件 {filename} 共 {len(texts)} 条文本")
        return batch_add_texts(texts)
    except Exception as e:
        logger.error(f"批量处理文本失败: {e}")
        traceback.print_exc()# 打印完整错误堆栈信息
        return False


def main(): # 主程序
    logger.info("开始启动 Neo4j 容器...")
    start_neo4j_container()
    logger.info("Neo4j 容器启动成功")
    
    try:
        print("请选择输入方式：")
        print("1 - 手动输入文本")
        print("2 - 从文件读取文本")
        choice = input("请输入 1 或 2：").strip()

        if choice == "1":
            print("请输入要处理的文本（每行一段，输入空行结束）：")
            texts = []
            while True:
                text = input("> ")
                if not text.strip():
                    break
                texts.append(text.strip())

            if not texts:
                print("未输入任何文本，使用默认测试文本。")
                texts = [
                    "你好，我是娜迦。"
                ]

            success = batch_add_texts(texts)

        elif choice == "2":
            filename = input("请输入文件路径：").strip()
            success = batch_add_from_file(filename)

        else:
            print("无效输入，仅支持 1 或 2。程序退出。")
            return

        if success:
            main_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(main_dir)
            graph_path = os.path.join(parent_dir, "logs", "knowledge_graph", "graph.html")
            webbrowser.open("file:///" + graph_path)
            print("\n知识图谱已生成：logs/knowledge_graph/graph.html")
            print("请输入查询问题（输入空行退出）：")
            while True:
                query = input("> ")
                if not query.strip():
                    print("退出查询。")
                    break
                result = query_knowledge(query)
                print("\n查询结果：")
                print(result)
                print("\n请输入下一个查询问题（输入空行退出）：")
        else:
            print("文本处理失败，请检查控制台日志。")

    except KeyboardInterrupt:
        logger.info("用户中断程序")
        print("\n程序已中断。")
    except Exception as e:
        logger.error(f"主程序运行失败: {e}")
        print(f"发生错误：{e}")


if __name__ == '__main__':
    main()
