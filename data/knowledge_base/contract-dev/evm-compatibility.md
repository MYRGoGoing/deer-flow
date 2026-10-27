---
title: EVM 兼容说明
category: contract-dev
source: 示例语料（公开资料整理）
---

# EVM 兼容说明

Hyperchain 内置兼容以太坊虚拟机（EVM），支持 Solidity 智能合约的部署与调用。

## 支持范围

- Solidity 0.8 及以下主流版本编写的合约。
- 标准 ERC-20、ERC-721 等代币合约可直接迁移。
- 通过 Remix 编译产出的字节码与 ABI 可直接部署。

## 与以太坊的差异

1. **共识不同**：以太坊为 PoS 公链共识，Hyperchain 为 RBFT 联盟链共识，无挖矿概念。
2. **账户体系**：沿用地址模型，但账户创建依赖联盟准入与证书。
3. **Gas 机制**：Gas 计费策略由联盟管理员配置，可整体关闭计费或设置固定 GasPrice。

## 工具链复用

开发者可继续使用 web3.js、web3.py 等标准 SDK 对接，仅需将 RPC 端点指向 Hyperchain 节点，并在 JSON-RPC 请求中携带 `namespace` 字段。

## 适用建议

需要复用以太坊成熟开源合约（如 Uniswap V2 数学库、OpenZeppelin 组件）时优先选择 EVM；涉及高频调用与复杂业务对象时，HVM 的 Java 合约通常更易维护。
