# -*- coding: utf-8 -*-
import json
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from llm_stream_json_parser_langchain import (
    IncrementalJSONCore,
    IncrementalJSONCallbackHandler,
    IncrementalJSONOutputParser
)

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

load_dotenv(dotenv_path=".env.api_key")
key = os.getenv("DEEPSEEK")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def sse_format(data: dict) -> str:
    return f"event: message\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/stream")
async def stream(concept: str):

    async def event_generator():

        # ------------- 1. 初始化模型 -------------------
        model = ChatOpenAI(
            model="deepseek-v3-250324",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=key,
            temperature=0,
            streaming=True,
        )

        prompt = ChatPromptTemplate.from_template(
            """
            请严格输出 JSON：
            {{
                "concept": "{concept}",
                "explanation": "<请用中文解释这个概念>",
                "examples": ["示例1", "示例2", "示例3","示例n"]
            }}
            """
        )

        # ------------- 2. 初始化增量解析器 -------------------
        core = IncrementalJSONCore()
        parser = IncrementalJSONOutputParser(core)
        callback = IncrementalJSONCallbackHandler(core)

        # ❗❗❗ 关键点：不要接 parser，否则流式就被截断了
        workflow = prompt | model

        # ------------- 3. 流式 Token 输出 -------------------
        async for token in workflow.astream(
            {"concept": concept},
            config={"callbacks": [callback]}
        ):
            # 每一次 token 到达，callback 已更新 snapshot
            yield sse_format(core.snapshot())

        # ------------- 4. 最终 end 数据 -------------------
        final = parser.parse(core.buffer)
        yield sse_format(final)

        yield "event: close\ndata: done\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("llm_stream_json_parser_fastapi:app", host="0.0.0.0", port=8001, reload=True)
