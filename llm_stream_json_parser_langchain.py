# -*- coding: utf-8 -*-
import json
import re
import asyncio

#加载环境变量
import os
from dotenv import load_dotenv

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.output_parsers import BaseOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from pydantic import Field, ConfigDict





# ======================================================
# 1. 增量 JSON 核心解析器
# ======================================================
class IncrementalJSONCore:
    """
    负责：
    - 累积 LLM chunk
    - 增量提取 concept / explanation / examples
    - 返回流式 snapshot（state=loading）
    - 返回最终结构（state=end）
    """

    def __init__(self):
        self.buffer = ""
        self.result = {
            "concept": None,
            "explanation": None,
            "examples": []
        }
        self.seen_examples = set()

    # ---------- 增量解析 ----------
    def feed(self, chunk: str):
        self.buffer += chunk

        # ----- concept -----
        m = re.search(r'"concept"\s*:\s*"([^"]*)', self.buffer)
        if m:
            self.result["concept"] = m.group(1)

        # ----- explanation -----
        m = re.search(r'"explanation"\s*:\s*"([^"]*)', self.buffer)
        if m:
            self.result["explanation"] = m.group(1)

        # ----- examples -----
        m = re.search(r'"examples"\s*:\s*\[([^\]]*)', self.buffer)
        if m:
            arr = m.group(1)
            elems = re.findall(r'"([^"]+)"', arr)
            for e in elems:
                if e not in self.seen_examples:
                    self.seen_examples.add(e)
                    self.result["examples"].append(e)

    # ---------- 最终 JSON ----------
    def final_json_raw(self):
        try:
            return json.loads(self.buffer)
        except:
            return None

    # ---------- 流式输出（state=loading） ----------
    def snapshot(self):
        return {
            "state": "loading",
            "result": self.result
        }

    # ---------- 最终输出（state=end） ----------
    def result_end(self):
        final = self.final_json_raw()
        return {
            "state": "end",
            "result": final if final else self.result
        }
# ======================================================
# 3. LangChain OutputParser：最终返回 state=end
# ======================================================
class IncrementalJSONOutputParser(BaseOutputParser):
    """
    - LCEL 链末尾执行 parse()
    - 必须定义 pydantic model_config，否则会报错
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    parser_core: IncrementalJSONCore = Field(exclude=True)

    def __init__(self, parser_core: IncrementalJSONCore):
        super().__init__(parser_core=parser_core)

    def parse(self, text: str):
        # 最终一次性喂所有文本
        self.parser_core.feed(text)
        return self.parser_core.result_end()

    @property
    def _type(self):
        return "incremental-json-parser"


# ======================================================
# 2. LangChain Callback：流式增量解析
# ======================================================
class IncrementalJSONCallbackHandler(AsyncCallbackHandler):
    """
    每接收一个 token → 自动调用 feed() → 推送 snapshot
    """

    def __init__(self, core: IncrementalJSONCore):
        self.core = core

    async def on_llm_new_token(self, token: str, **kwargs):
        self.core.feed(token)
        print("[INCREMENTAL STATE]:", self.core.snapshot())




# ======================================================
# 4. 可运行示例：DeepSeek 流式输出 + 增量解析
# ======================================================
async def run_demo():
    load_dotenv(dotenv_path=".env.api_key")
    api_key = os.getenv("DEEPSEEK")
    if not api_key:
        print("❌ 请在 .env 文件中设置 DEEPSEEK=你的APIKey")
        return

    # ---- DeepSeek 模型 ----
    model = ChatOpenAI(
        model="deepseek-v3-250324",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key=api_key,
        temperature=1,
        streaming=True,
    )
    # ChatOpenAI 常用参数说明：
    # 3.1 OpenAI 相关参数
    # --------------------------------------------------
    # model:           必填，要调用的模型名，例如 "gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini" 等。
    # api_key:         可选，OpenAI API Key。如果不传，会默认从环境变量 OPENAI_API_KEY 中读取。
    # base_url:        可选，请求的 API 基础地址。默认是 OpenAI 官方地址；如果你连接的是兼容服务（自建 vLLM、OpenRouter、LM Studio、Ollama 等）需要改成对应地址。
    # organization:    可选，组织 ID，对应环境变量 OPENAI_ORG_ID。

    # 3.2 通用请求控制参数
    # --------------------------------------------------
    # temperature:     采样温度，控制输出的“随机性/创造性”。——默认为 0.7。:contentReference[oaicite:1]{index=1}
    #                   - 取值一般在 0–1 之间。
    #                   - 越低越稳定、保守（适合严谨任务）。
    #                   - 越高越富创意、发散。
    # max_tokens:      回复中允许生成的最大 token 数。——默认为 None（即不主动限制，使用服务默认）:contentReference[oaicite:2]{index=2}
    # top_p:           nucleus sampling 的截断概率。——若未显式设置，通常不会作为参数发送；在 LangChain 中可能需通过 model_kwargs 传递。:contentReference[oaicite:3]{index=3}
    # timeout (或 request_timeout): 请求超时时间（单位：秒）。——默认为 600 秒。:contentReference[oaicite:4]{index=4}
    # max_retries:     当出现网络错误或服务端 5xx 错误时，自动重试的最大次数。——默认值为 6。:contentReference[oaicite:5]{index=5}
    # streaming:       是否流式返回 token。——默认为 False。:contentReference[oaicite:6]{index=6}
    # n:               每次提示生成多少个完成（choices 数量）。——默认值为 1。:contentReference[oaicite:7]{index=7}

    prompt = ChatPromptTemplate.from_template(
        """
        请严格输出 JSON：
        {{
            "concept": "{concept}",
            "explanation": "<请用中文解释>",
            "examples": ["示例1", "示例2", "示例3"]
        }}
        """
    )

    # ---- 初始化解析器组件 ----
    core = IncrementalJSONCore()
    parser = IncrementalJSONOutputParser(core)
    callback = IncrementalJSONCallbackHandler(core)

    chain = prompt | model | parser

    print("\n========== 开始流式解析 ==========\n")

    async for _ in chain.astream(
        {"concept": "LangChain Expression Language"},
        config={"callbacks": [callback]}
    ):
        pass

    print("\n========== 最终 JSON（state=end） ==========\n")
    final = parser.parse(core.buffer)
    print(json.dumps(final, ensure_ascii=False, indent=2))


# ======================================================
# main
# ======================================================
if __name__ == "__main__":
    asyncio.run(run_demo())
