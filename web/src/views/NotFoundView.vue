<template>
  <div class="not-found">
    <div class="code">404</div>
    <h2>页面走丢了</h2>
    <p>您访问的页面不存在，或者已被移除</p>
    <el-button type="primary" @click="$router.replace('/chat')">返回首页</el-button>
  </div>
</template>

<script setup></script>

<style lang="scss" scoped>
.not-found {
  height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 24px;
  .code {
    font-size: 120px;
    line-height: 1;
    font-weight: 900;
    background: linear-gradient(135deg, #4f46e5, #06b6d4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  h2 {
    margin: 12px 0 6px;
    font-size: 24px;
  }
  p {
    margin: 0 0 24px;
    color: var(--app-text-muted);
  }
}
</style>
