<script setup>
import {ref} from 'vue'

// 输入框内容
const concept = ref("")

// 流式输出内容
const messages = ref([])

// 是否加载中
const isStreaming = ref(false)

const user_select = ref([])

// 绑定 SSE EventSource
let es = null

const state = ref("")
const user = ref("")
const explanation = ref("")
const examples = ref([])
// 开始流式请求
const startStream = () => {
  if (!concept.value.trim()) {
    alert("请输入概念内容")
    return
  }

  messages.value = []
  isStreaming.value = true

  // 关闭上一次的连接
  if (es) es.close()

  // 创建 SSE 连接
  es = new EventSource(
      `http://localhost:8001/stream?concept=${encodeURIComponent(concept.value)}`
  )

  // 监听增量输出
  es.onmessage = (event) => {
    try {
      messages.value = JSON.parse(event.data)
      state.value = messages.value.state
      user.value = messages.value.result.concept
      explanation.value = messages.value.result.explanation
      examples.value = messages.value.result.examples

    } catch (err) {
      console.error("解析失败:", event.data)
    }
  }

  // 流结束
  es.addEventListener("close", () => {
    isStreaming.value = false
    es.close()
  })

  // 出错时
  es.onerror = () => {
    console.log("SSE 连接出错")
    isStreaming.value = false
    es.close()
  }
}
</script>


<template>
  <div style="padding: 20px; max-width: 800px; margin: 0 auto;">

    <h1>DEMO 1</h1>

    <div v-if="user_select.length>0">已选:
      <div v-for="item in user_select" style="margin-top:10px;background-color: beige">
        {{examples[item]}}
      </div>
    </div>

    <!-- 输入框 -->
    <div style="margin-bottom: 20px;margin-top:20px">
      <input
          v-model="concept"
          placeholder="请输入概念，例如：LangChain Expression Language"
          style="width: 100%; padding: 10px; font-size: 16px;"
      />
    </div>

    <!-- 按钮 -->
    <button
        @click="startStream"
        style="
        padding: 10px 20px;
        background: #42b883;
        border: none;
        color: white;
        cursor: pointer;
        font-size: 16px;
      "
        :disabled="isStreaming"
    >
      {{ isStreaming ? '请求中...' : '获取答案' }}
    </button>

    <hr style="margin: 20px 0;" />

    <!-- 流式输出 -->
    <h2>结构化输出：</h2>

<!--    <div-->
<!--        v-for="(msg, index) in messages"-->
<!--        :key="index"-->
<!--        style="-->
<!--        background: #f4f4f4;-->
<!--        margin-bottom: 10px;-->
<!--        padding: 10px;-->
<!--        border-radius: 5px;-->
<!--        font-family: monospace;-->
<!--        white-space: pre-wrap;-->
<!--        word-break: break-word;-->
<!--      "-->
<!--    >-->
<!--      {{ JSON.stringify(msg, null, 2) }}-->
<!--    </div>-->
  <div v-if="state === 'loading'">加载中...</div>
    <div v-if="user" style="text-align: justify;text-align-last: center">问题:{{user}}</div>
    <div v-if="explanation" style="margin-top:20px;text-align: justify;text-align-last: center">解释:{{explanation}}</div>
    <div v-if="examples.length>0" style="display: flex;flex-direction: column;gap: 20px;margin-top: 20px;">
      <div>示例:</div>
      <div  v-for="(item,index) in examples" :key = "index" >
        <div v-if="!user_select.includes(index)" style="background-color: #747bff;color: white" @click="user_select.push(index)">{{item}}</div>
      </div>

    </div>
<!--    <div>{{messages}}</div>-->

  </div>
</template>


<style scoped>
h1 {
  margin-bottom: 10px;
}
</style>
