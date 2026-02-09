import asyncio # 导入异步IO库，用于实现异步编程
import os # 导入操作系统模块，在本项目中用于读取环境变量文件
import webbrowser # 导入web浏览器模块，在本项目中用户打开一个web页面展示翻译后的文档内容
import tempfile # 导入临时文件模块，在本项目中用于生成临时HTML文件以在浏览器中显示
from nagaagent_core.vendors import markdown # 导入markdown库，在本项目中用于格式化文档内容并显示
import traceback # 用于捕获和打印详细的异常信息
from typing import Any # 导入类型提示工具，增加代码的类型安全，在本项目中用于标记函数参数和返回值的类型

# OpenAI Agents SDK 相关导入
from nagaagent_core.vendors.agents import (
  Agent, # Agent类，用于定义和执行Agent任务，本项目中我们需要构建浏览器、文档处理和控制器代理
  Model, # Model类，用于定义我们自定义的模型提供商函数返回的类型
  ModelSettings, # ModelSettings类，用于配置模型参数，如温度等，在本项目中用于调整各代理的行为特征
  RunConfig, # 在本项目中用于配置运行环境和追踪选项
  Runner, # 在本项目中用于启动和协调 agent 的运行
  set_tracing_disabled, # 禁用追踪功能的函数，避免发送数据到 OpenAI
  function_tool, # 在本项目中用于创建一个markdown浏览器工具，让 agent 使用
  ModelProvider, # 在本项目中用于实现 DeepSeek API 兼容的实例
  OpenAIChatCompletionsModel, # 在本项目中用于连接DeepSeek API
  RunContextWrapper, # 在本项目中用于钩子函数参数的类型进行定义
  AgentHooks, # agent 生命周期钩子接口，用于监控和干预 agent 执行过程，在本项目中用于追踪执行进度和提取执行结果
)

try:
    from nagaagent_core.vendors.agents.mcp import MCPServerStdio  # 优先从代理导入 #
except Exception:
    MCPServerStdio = None  # 兼容缺失 #
from nagaagent_core.core import AsyncOpenAI # 导入OpenAI 异步客户端，在本项目中用于创建于 Deepseek API 的异步通信客户端
from nagaagent_core.core import load_dotenv # 导入dotenv库，在本项目中用于加载环境变量文件

load_dotenv() # 加载环境变量文件

# 禁用追踪以避免需要 Openai API 密钥
# 这是为了防止SDK默认向OpenAI发送追踪数据进行agent调试，因为我们使用的是 DeepSeek API，是没有OpenAI API密钥的，防止它自动请求 OpenAI API
set_tracing_disabled(True)

# 从config.json文件中读取配置
try:
    from system.config import load_config
    config = load_config()
    API_KEY = config.api.api_key # 从config.json中读取API_KEY
    BASE_URL = config.api.base_url # 从config.json中读取BASE_URL
    MODEL_NAME = config.api.model # 从config.json中读取MODEL_NAME
    print(f"✅ 从config.json加载配置成功: {MODEL_NAME}")
except Exception as e:
    print(f"❌ 从config.json加载配置失败: {e}")
    # 如果config加载失败，尝试从环境变量读取（兼容性）
    API_KEY = os.getenv("API_KEY")
    BASE_URL = os.getenv("BASE_URL")
    MODEL_NAME = os.getenv("MODEL_NAME")
    print(f"⚠️ 使用环境变量配置: {MODEL_NAME}")

# 验证必须的配置是否存在
if not API_KEY:
    raise ValueError("API_KEY 未在config.json或环境变量中设置")
if not BASE_URL:
    raise ValueError("BASE_URL 未在config.json或环境变量中设置")
if not MODEL_NAME:
  MODEL_NAME = "deepseek-chat"


client = AsyncOpenAI(
  base_url=BASE_URL, # 使用自定义的API基础URL，指向DeepSeek服务器地址
  api_key=API_KEY, # 使用自定义的API密钥，指向 DeepSeek API 密钥
)

# 模型提供商的类
class DeepSeekModelProvider(ModelProvider):
  """
  自定义模型提供商

  实现 ModelProvider 接口，提供自定义模型实例
  这使应用程序可以使用DeepSeek等于Openai兼容的API替代原生openai接口
  在本项目中，它作为所有agents于模型交互的统一入口，确保一致性的模型行为
  """
  # 实现 ModelProvider 接口的 get_model 方法
  def get_model(self, model_name: str) -> Model:
    """
    获取模型实例
    根据提供的模型名称创建并返回一个模型实例

    参数:
      model_name (str): 模型名称

    返回:
      Model: 一个OpenAI兼容的模型实例
    """
    return OpenAIChatCompletionsModel(model=model_name or MODEL_NAME, openai_client=client)

# 创建模型提供商实例
# 这个实例将被用于所有 agent 与模型交互
model_provider = DeepSeekModelProvider()

@function_tool
async def open_markdown_in_browser(content: str, title: str="文档标题") -> str:
    """
    将Markdown内容转换为HTML并在浏览器中打开展示

    这个工具将markdown内容转换为HTML格式，创建一个临时的HTML文件，
    并在用户默认浏览器中打开它，方便查看格式化后的文档。

    在本项目中，它是文档处理 agent 的输出工具，用于将翻译后的GitHub文档以美观的方式呈现给用户，提供良好的阅读体验。

    args:
      content (str): markdown格式的文档内容，包含翻译后的技术文档
      title (str): 文档标题，显示在浏览器标签页和页面顶部

    returns:
      str: 打开结果消息，包含成功或失败的状态信息
    """

    try:
        # 检查内容是否以标题开头，避免重复标题
        first_line = content.strip().split("\n", 1)[0]
        has_title_in_content = first_line.startswith('# ') and first_line[2:].strip() == title

        # 创建临时的HTML文件
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                h1, h2, h3, h4, h5, h6 {{
                    margin-top: 24px;
                    margin-bottom: 16px;
                    font-weight: 600;
                    color: #0366d6;
                }}
                h1 {{ font-size: 2em; border-bottom: 1px solid #eaecef; padding-bottom: .3em; }}
                h2 {{ font-size: 1.5em; border-bottom: 1px solid #eaecef; padding-bottom: .3em; }}
                code {{
                    font-family: SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace;
                    background-color: rgba(27, 31, 35, .05);
                    border-radius: 3px;
                    padding: .2em .4em;
                }}
                pre {{
                    background-color: #f6f8fa;
                    border-radius: 3px;
                    padding: 16px;
                    overflow: auto;
                }}
                pre code {{
                    background-color: transparent;
                    padding: 0;
                }}
                blockquote {{
                    margin: 0;
                    padding: 0 1em;
                    color: #6a737d;
                    border-left: .25em solid #dfe2e5;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                }}
                table th, table td {{
                    padding: 6px 13px;
                    border: 1px solid #dfe2e5;
                }}
                table tr {{
                    background-color: #fff;
                    border-top: 1px solid #c6cbd1;
                }}
                table tr:nth-child(2n) {{
                    background-color: #f6f8fa;
                }}
                /* 添加图片大小控制 */
                img {{
                    max-width: 100%;
                    height: auto;
                    display: block;
                    margin: 1.5em 0;
                }}
            </style>
        </head>
        <body>
            {'' if has_title_in_content else f'<h1>{title}</h1>'}
            {markdown.markdown(content, extensions=['extra', 'codehilite', 'tables', 'fenced_code'])}
        </body>
        </html>
        """
        
        # 创建临时的HTML文件
        fd, path = tempfile.mkstemp(suffix=".html")
        # 写入HTML内容到临时文件
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(html_content)

        # 使用playwright打开浏览器
        webbrowser.open(f"file://{path}")

        return f"文档已成功在浏览器中打开: {path}"
    except Exception as e:
        print(f"打开浏览器失败: {e}")
        traceback.print_exc()
        return f"打开浏览器失败: {str(e)}"

class BrowserAgentHooks(AgentHooks):
    """
    用于监控浏览器agent执行的钩子

    这个类实现了 AgentHooks 接口，用于监控和处理浏览器agent的生命周期事件。
    主要功能是：
    1.跟踪 agent 执行开和结束
    2.解析 agent 返回的markdown格式数据
    3.提取github仓库信息和文档内容
    4.保存这些数据以便后续处理和分析

    在本项目中，它是连接浏览器agent和文档处理agent的关键环节，负责从浏览器代理返回结果中提取结构化数据
    """

    def __init__(self):
        self.extracted_repos = []  # 保存提取的仓库数据，存储解析后的仓库元数据
        self.extracted_docs = []   # 保存提取的文档数据，存储解析后的文档内容和元数据

    async def on_start(self, context: RunContextWrapper, agent: Agent) -> None:
        """
        当 agent 开始运行时出发
        """
        print(f"[浏览器代理] {agent.name} 开始执行。。。")

    async def on_end(self, context: RunContextWrapper, agent: Agent, output: Any) -> None:
        """
        当 agent 结束运行时触发
        """
        print(f"[浏览器代理] {agent.name} 完成执行，执行结果: \n {output[:300]}")

class DocProcessorHooks(AgentHooks):
    """
    用于监控文档处理 agent 执行时的钩子

    这个类实现 agentHooks 接口，用于监控文档处理 agent 的生命周期事件。
    这个钩子的主要功能是记录文档处理 agent 执行的开始和结束。
    方便追踪整个文档翻译和处理流程。

    在本项目中，它作为文档处理阶段的监控组件，提供文档翻译过程的可视化追踪。
    """

    async def on_start(self, context: RunContextWrapper, agent: Agent) -> None:
        """
        当 agent 开始运行时触发
        """
        print(f"[文档处理代理] agent {agent.name} 开始执行。。。")
    async def on_end(self, context: RunContextWrapper, agent: Agent, output: Any) -> None:
        """
        当 agent 结束运行时触发
        """
        print(f"[文档处理代理] agent {agent.name} 完成执行，执行结果: \n {output}")


async def create_browser_agent():
    """
    创建浏览器交互 agent

    这个函数负责初始化和配置浏览器交互 agent 包括：
    1. 创建 playwright MCP 服务连接实例
    2. 配置浏览器agent，包括指令和模型设置
    3. 设置监控钩子用于显示执行结果

    浏览器 agent 负责使用 playwright 打开浏览器访问GITHub，搜索并提取用户指定技术的相关文档。
    在本项目中，此函数创建了负责网络交互的 agent，是整个工作流的第一个关键组件。

    Returns:
        tuple: (浏览器代理实例, Playwright MCP服务器连接实例)
    """
    # 创建 playwright MCP 服务连接实例,使用 MCPServerStdio 标准输入输出通信。
    if MCPServerStdio is None:
        raise RuntimeError("MCPServerStdio 不可用，请安装 agents SDK 或提供本地替代实现")
    playwright_server = MCPServerStdio(
        name="playwright",  # 服务名称，用于标识此MCP服务
        params={
            "command": "npx",  # 运行npx命令
            "args": ["-y", "@playwright/mcp@latest"],  # 启动最新版的Playwright MCP服务
            "env": {
                "PLAYWRIGHT_BROWSERS_PATH": "0",  # 使用系统安装的浏览器
                "PLAYWRIGHT_DEFAULT_BROWSER": "msedge"  # 指定使用Edge浏览器
            }  # 环境变量，指定使用Edge浏览器
        },
        cache_tools_list=True  # 缓存工具列表，减少重复查询开销
    )

    try:
        # 连接 playwright MCP 服务
        print("正在连接 playwright MCP 服务...")
        await playwright_server.connect()
        print("playwright MCP 服务连接成功")

        # 获取 MCP 服务可用工具列表
        tools = await playwright_server.list_tools()
        print(f"playwright MCP 服务可用工具列表: {len(tools)} 个工具")

        # 创建浏览器 agent 钩子
        # 用于监控和处理浏览器 agent 的执行过程和结果，在项目中作为 agent 生命周期的监控组件
        browser_hooks = BrowserAgentHooks()

        # 创建浏览器 agent
        # 配置一个专门用于github文档检索的智能代理，在项目中负责网络爬取和信息提取
        browser_agent = Agent(
            name="GitHubDocumentBrowser", # 代理名称，作为代理的唯一标识符
            # 详细的 agent 指令，指导这个 agent 在github上进行文档检索，在项目中定义了 agent 的执行策略和行为规划
            instructions="""
            你是一个专业的GitHub文档检索专家。你的任务是使用浏览器工具访问GitHub，搜索用户指定的技术关键词，并提取最权威、最直接相关的官方仓库文档内容。

            按照以下步骤工作：
            1. 导航到GitHub (https://github.com)
            2. 使用GitHub的搜索功能，搜索指定的技术关键词
                - 优先考虑搜索语法：[技术名称] org:[官方组织]
                - 例如搜索"openai agent"应优先尝试"agent org:openai"
                - 对于知名项目，始终优先选择官方组织的仓库，而非第三方实现或衍生项目
            3. 从搜索结果中选择1个最相关的仓库，遵循以下优先级：
                a. 官方组织发布的直接相关仓库（如openai组织的openai-agent相关仓库）
                b. 技术拥有者的官方仓库，而非第三方实现
                c. 星标数高的权威仓库
                d. 与搜索关键词在名称或描述中直接匹配的仓库
            4. 对该仓库：
               a. 收集仓库基本信息（所有者、名称、描述、星标数等）
               b. 仅获取README文件内容，不要获取多个文档
               c. 只有当README不存在或内容极少时，才获取一个替代核心文档（如快速入门）
            5. 将结果按照下面的格式直接返回给调用你的控制器
           
            注意：你的唯一任务是获取文档并按格式返回结果，不要尝试执行额外的操作或调用其他代理。
           
            **返回格式（必须严格按照以下结构）：**
           
            ## 仓库信息
            - 名称：[仓库名称]
            - 所有者：[仓库所有者]
            - 描述：[仓库描述]
            - 星标数：[星标数]
            - URL：[仓库URL]
           
            ## 文档信息
            ### [文档标题]
            - URL：[文档URL]
           
            ### 内容：
            [文档内容]
           
            **重要限制和说明：**
            1. 严格按照上面的格式返回信息，不要添加额外的说明或解释
            2. 优先选择权威官方仓库，避免选择第三方实现或克隆项目
            3. 文档内容保持原始格式，包括Markdown标记
            4. 严格限制为单个仓库的单个文档，即使其他文档看起来也很重要
            5. 确保所选仓库与搜索关键词直接相关，避免选择仅仅提到关键词的非核心项目
            6. 如果文档内容tokens超过60000，那就把内容进行精简处理
            """,
            mcp_servers=[playwright_server],  # 关联MCP服务器，提供浏览器自动化能力
            hooks=browser_hooks, # 关联代理生命周期钩子，用于代理执行过程监控，处理执行结果和状态变化
            model=model_provider.get_model(MODEL_NAME), # 使用我们自定义的模型提供商获,确保agent使用正确的模型
            model_settings=ModelSettings(
                temperature=0.3, # 设置较低的温度值，增加输出的确定性，减少随机性，让 agent 行为更可预测
                top_p=0.9, # 设置top_p参数, 词汇多样性，影响生成内容的多样性
                tool_choice="auto", # 设置工具选择策略，自动选择最适合的工具
            )
        )

        return browser_agent, playwright_server
    
    except Exception as e:
        print(f"创建浏览器 agent 时发生错误: {e}")
        await playwright_server.cleanup() # 确保清理 MCP 服务器资源，防止资源泄露和进程残留

async def create_doc_processor_agent():
    """
    创建文档处理 agent

    这个函数负责初始化和配置文档处理 agent 包括：
    1. 接收从 GitHub 提取的英文技术文档
    2. 将文档翻译成中文
    3. 格式化并优化文档结构
    4. 调用 工具(open_markdown_in_browser) 在浏览器中展示处理后的结果

    文档处理 agent 作为工作流的第二阶段，接收浏览器 agent 提取的原始英文文档，将其转换为友好的中文格式。

    在本项目中，此函数创建翻译和展示文档的核心组件，实现了多语言内容适配。

    returns:
        Agent: 配置好的文档处理 agent 实例
    """

    # 创建文档处理 agent 钩子，用于监控和记录文档 agent 的执行过程，在项目中跟踪翻译任务的执行状态
    doc_hooks = DocProcessorHooks()

    # 创建文档处理 agent
    # 配置一个专门用于文档翻译和展示的智能代理，在项目中负责文档的翻译和格式化
    doc_processor_agent = Agent(
        name="DocumentProcessor", # 代理名称，作为代理的唯一标识符
        # 当一个 agent 通过 handoffs=[agent1,agent2] 被添加到另一个 agent 时
        # 模型会根据这个描述决定是否要交接给该代理，这个描述帮助模型理解每个代理的专长，以便做出正确的交接决策
        # 在本项目中用于告诉控制器 agent 应该何时启用文档 agent 处理相关的任务
        handoff_description="""专门接收英文技术文档并将其翻译成中文、格式化、添加摘要的专家代理，能处理标准结构化文档并在浏览器中展示结果""",
        instructions="""
        你是一个专业的技术文档处理专家。你的任务是接收从GitHub提取的英文技术文档，将其翻译成中文，并整理成一份结构清晰的Markdown格式文档。
       
        你会收到以下格式的输入：
       
        ## 仓库信息
        - 名称：[仓库名称]
        - 所有者：[仓库所有者]
        - 描述：[仓库描述]
        - 星标数：[星标数]
        - URL：[仓库URL]
       
        ## 文档信息
        ### [文档标题]
        - URL：[文档URL]
       
        ### 内容：
        [英文文档内容]
       
        对于接收到的文档，你需要：
        1. 翻译标题和内容（代码块内的代码不需要翻译）
        2. 保持原始的标题层级和格式
        3. 保留代码块，不翻译代码
        4. 提供一个简短的文档摘要
        5. 针对中文读者优化表达方式
       
        完成翻译后，使用open_markdown_in_browser工具在浏览器中展示结果。
       
        请仔细检查以下内容：
        1. 检查译文的准确性和流畅性
        2. 确保专业术语的翻译一致
        3. 保留原文的重要格式和结构
        """,
        tools=[open_markdown_in_browser], # 添加我们自定义的工具，用于在浏览器中展示翻译后的文档
        hooks= doc_hooks, # 关联代理生命周期钩子，用于代理执行过程监控，跟踪翻译任务状态变化
        model=model_provider.get_model(MODEL_NAME), # 使用我们自定义的模型提供商获,确保agent使用正确的模型
        model_settings=ModelSettings(
            temperature=0.6, # 相对较高的温度，使翻译更有创造性和自然性，在项目中增强翻译文本的可读性
            top_p=0.9, # 设置top_p参数, 词汇多样性，影响生成内容的多样性
            tool_choice="auto", # 设置工具选择策略，自动选择最适合的工具
        )
    )
    return doc_processor_agent
    
async def create_controller_agent(browser_agent: Agent, doc_processor_agent: Agent):
    """
    创建主控制代理

    这个函数负责初始化和配置主控制代理，该代理负责：
    1. 协调整个工作流程
    2. 管理从 GitHub检索文档到翻译处理的完整流程
    3. 确保整个系统有序的完成所有任务

    控制器代理是整个系统的核心组件，它通过工具调用和交接功能，
    将用户查询转换为一系列协调的任务，最终生成翻译好的文档。

    Args:
        browser_agent: 浏览器交互 agent 实例,用于github文档检索
        doc_processor_agent: 文档处理 agent 实例,用于文档翻译和格式化展示

    Returns:
        agent: 配置好的控制器 agent 实例
    """
    # 使用 as_tool 方法将 agent 转换为工具，确保直接调用
    # 当 agent 被转换为工具时使用，告诉模型这个工具的功能和用途，模型根据这个描述决定何时调用该工具
    browser_tool = browser_agent.as_tool(
        tool_name="search_github_docs", #工具名称，模型通过此名称调用工具
        tool_description="根据用户指定的技术关键词，在GitHub上搜索并获取一个最相关、星标数最多的仓库信息及其文档内容。输出包含标准格式的仓库基本信息（名称、所有者、描述、星标数、URL）和README或关键文档的原始内容。此工具执行完整的浏览、搜索、选择和提取过程，返回的信息将用于后续翻译处理。"
    )

    # 创建控制器 agent
    # 这是整个工作流的核心，负责协调检索和翻译过程
    controller_agent = Agent(
        name="playwright_controller", # 修改为与manifest匹配的名称
        # agent 指令
        instructions="""
        你是GitHub技术文档检索和翻译系统的控制器。你的任务是协调整个工作流程，确保从GitHub检索文档
        并将其翻译整理成Markdown格式的流程顺利完成。
       
        工作流程：
        1. 首先，理解用户的技术查询需求
        2. 使用search_github_docs工具在GitHub上搜索并提取相关技术文档
        3. 获取到文档内容后，必须立即将完整的文档内容传递给DocumentProcessor代理进行处理
           (使用transfer_to_documentprocessor工具并传递完整的文档内容)
        4. 等待DocumentProcessor完成翻译和格式化
        5. 向用户报告最终结果
       
        重要提示：
        - 你必须完成整个流程的所有步骤
        - 在收到GitHubDocumentBrowser的结果后，必须将其传递给DocumentProcessor
        - 不要自行处理或修改文档内容，你的工作是协调而非处理
        - 使用transfer_to_documentprocessor工具时，传递完整的原始文档内容
       
        你的成功标准是完成整个流程，确保文档被正确检索、翻译和格式化。
        """,
        tools=[browser_tool], # 浏览器 agent 作为工具提供给控制器 agent 使用
        handoffs=[doc_processor_agent], # 文档处理 agent 作为交接选项提供给控制器 agent
        model=model_provider.get_model(MODEL_NAME), # 使用我们自定义的模型提供商获,确保agent使用正确的模型
        model_settings=ModelSettings(
            temperature=0.1, # 定义非常低的温度值，使控制逻辑更确定性，减少随机性
            top_p=0.9, # 设置top_p参数, 词汇多样性，影响生成内容的多样性
            tool_choice="auto", # 设置工具选择策略，自动选择最适合的工具
        )
    )

    return controller_agent

async def handle_agent_manager_request(query: str) -> str:
    """
    处理AgentManager传递的消息的接口函数
    
    这个函数是playwright_controller接收AgentManager调用的入口点。
    当AgentManager调用playwright_controller时，会传递query参数，
    这个函数会调用process_user_query来处理具体的GitHub文档检索任务。
    
    Args:
        query (str): AgentManager传递的任务内容
        
    Returns:
        str: 处理结果，成功时返回翻译后的文档内容，失败时返回错误信息
    """
    try:
        print("========== Playwright控制器收到AgentManager请求 ==========")
        print(f"任务内容: {query}")
        
        # 直接调用process_user_query处理查询
        result = await process_user_query(query)
        
        print("========== Playwright控制器处理完成 ==========")
        return result
        
    except Exception as e:
        error_msg = f"Playwright控制器处理AgentManager请求时出错: {str(e)}"
        print(f"错误: {error_msg}")
        traceback.print_exc()
        return error_msg
    
async def process_user_query(query: str) -> str:
    """
    处理用户查询

    这个函数是整个应用的核心处理流程，负责：
    1.初始化所有的 agent 组件
    2.建立和协调 agent 之间的关系
    3.执行完整的文档检索和翻译工作流
    4.处理执行过程中的异常和资源清理

    工作流程以此为： 创建浏览器 agent -> 创建文档处理 agent -> 创建控制器 agent -> 
    执行 控制器 agent 协调整个流程 -> 处理和展示结果 -> 清理资源

    在本项目中，此函数是用户交互的入口函数，将用户的简单查询转化为完整的代理工作流。

    Args:
        query (str): 用户输入的查询，如：openai agent，playwright，python，

    Returns:
        str: 处理结果字符串，成功时返回翻译后的文档内容，失败时返回错误信息
    """
    playwright_server = None
    try:
        print("========== 开始处理用户查询 ==========")

        # 创建浏览器 agent
        # 负责使用 playwright 打开浏览器访问GitHub，搜索并提取用户指定技术的相关文档
        browser_agent, playwright_server = await create_browser_agent()
        print("浏览器 agent 创建成功")

        # 创建文档处理 agent
        # 负责将英文文档翻译成中文并格式化，在项目中实现内容转换和本地化处理
        doc_processor_agent = await create_doc_processor_agent()
        print("文档处理 agent 创建成功")

        # 创建控制器 agent
        # 负责协调整个工作流程，管理浏览器 agent 和 文档处理 agent 之间的交互，在项目中作为系统的调度中心
        controller_agent = await create_controller_agent(browser_agent, doc_processor_agent)
        print("控制器 agent 创建成功")

        for tool in controller_agent.tools:
            print(f"控制器 agent 可用工具: {tool.name}: {tool.description}")
        
        for handoff in controller_agent.handoffs:
            tool_name = f"transfer_to_{handoff.name.lower()}"
            print(f"控制器 agent 交接代理: {tool_name} > {handoff.name}")

        print(f"\n正在处理查询: '{query}'")
        print("这个操作可能需要几分钟时间...\n")

        result = await Runner.run(
            controller_agent,
            input=query,
            max_turns=50, # 设置最大回合数，防止无限循环
            run_config=RunConfig(
                trace_include_sensitive_data=False, # 不在追踪中包含敏感数据，保护隐私和敏感信息
            )
        )

        print("\n========== 任务完成 ==========")
        
        # 提取结果内容
        if hasattr(result, "final_output"):
            final_result = result.final_output
        elif hasattr(result, "output"):
            final_result = result.output
        else:
            final_result = str(result)
        
        print(f"\n工作流结果：{final_result[:200]}...")
        return final_result

        
    except Exception as e:
        error_msg = f"执行过程中出错: {e}"
        print(f"\n{error_msg}")
        traceback.print_exc()
        return error_msg
    
    finally:
        # 确保所有资源都被正确释放
        if playwright_server:
            print("正在释放 playwright 资源...")
            await playwright_server.cleanup()
            print("playwright 资源释放成功")

async def main():
    """
    主函数：

    这个函数实现了应用程序的交互命令行界面，负责：
    1.显示系统欢迎信息和使用说明
    2.处理用户输入的查询指令
    3.调用 process_user_query 函数处理用户查询
    4.处理用户退出命令和异常情况

    整个程序以循环方式运行，允许用户连接查询多个技术关键词，
    直到用户明确要求退出，所有异常都会被捕获并记录，确保程序稳定运行。

    在本项目中，此函数是用户界面的主入口，提供了一个简单的交互界面。
    """
    
    print("\n========== GitHub文档检索与翻译系统 ==========")
    print("输入技术关键词，系统将搜索并翻译相关文档")
    print("输入 'quit' 或 'exit' 退出系统")
    print("==============================================\n")

    try:
        while True:
            # 获取用户输入
            user_query = input("\n请输入想要搜索的技术关键词 或 输入 'quit' 退出系统: ").strip()

            # 检查用户是否想要退出
            if user_query.lower() in ["quit"]:
                print("感谢使用，再见！")
                break
            
            # 验证输入是否为空
            if not user_query.strip():
                print("查询内容不能为空，请重新输入")
                continue
            
            # 处理用户查询
            await process_user_query(user_query)

            print("\n输入新的查询或输入 'quit' 退出系统")

    except KeyboardInterrupt:
        print("\n用户手动退出,正在退出...")
    except Exception as e:
        print(f"\n程序运行时发生错误: {e}")
        traceback.print_exc()
    finally:
        print("\n程序结束，所有资源已释放。")

# 程序入口点
if __name__ == "__main__":
    asyncio.run(main())