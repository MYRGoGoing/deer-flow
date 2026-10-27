---
title: JSON-RPC 接口基础
category: api-reference
source: 示例语料（公开资料整理）
---

# JSON-RPC 接口基础

Hyperchain 节点对外提供 JSON-RPC 2.0 标准接口，HTTP 与 WebSocket 两种通道均可访问。

## 请求格式

```json
{
  "jsonrpc": "2.0",
  "namespace": "global",
  "method": "tx_getTransactionCount",
  "params": ["0x{account}", false],
  "id": 1
}
```

`namespace` 字段指定目标账本，省略时默认 `global`。

## 方法分类

### 交易类

- 提交签名交易：将签名后的原始交易广播上链，返回交易哈希。
- 查询账户 nonce：构造交易前获取账户交易计数。

### 查询类

- 按哈希查交易详情与回执。
- 按高度查区块及其交易列表。
- 查询最新区块高度。

### 合约类

- 部署合约：提交字节码，返回合约地址。
- 调用合约：指定合约地址、方法与参数发起调用。
- 只读调用：本地模拟执行，不上链、不消耗 gas，适合查询型接口。

## 响应与错误

响应包含 result 或 error 字段。error 由 code 与 message 组成，常见错误包括参数非法、nonce 不匹配、余额不足与 gasLimit 过小等。批量请求可将多个调用放入数组一次提交，响应按序返回对应结果。
