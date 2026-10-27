---
title: HVM 合约开发指南
category: contract-dev
source: 示例语料（公开资料整理）
---

# HVM 合约开发指南

HVM（Hyperchain Virtual Machine）是自研的 Java 智能合约引擎，允许开发者使用 Java 语言编写合约，编译为字节码后部署到链上执行。

## 开发流程

1. 使用 JDK 8+ 编写合约类，引入 HVM 合约 SDK。
2. 以注解声明合约入口与可调用方法。
3. 编译打包为 jar 字节码。
4. 通过 JSON-RPC 的合约部署接口提交字节码。
5. 部署成功后获得合约地址，后续按地址调用。

## 合约基本结构

```java
@Contract
public class TokenContract {
    private Map<String, Long> balances = new HashMap<>();

    @Transaction
    public void transfer(String from, String to, long amount) {
        if (balances.getOrDefault(from, 0L) < amount) {
            throw new RuntimeException("insufficient balance");
        }
        balances.put(from, balances.get(from) - amount);
        balances.put(to, balances.getOrDefault(to, 0L) + amount);
    }
}
```

## 状态变量

合约类的成员变量即链上状态，修改随交易原子生效。支持的类型包括基础类型、String、POJO 以及其集合包装。

## 与 EVM 的关系

HVM 与 EVM 并列运行，同一 namespace 内的两类合约可以通过跨合约调用接口互相访问。需要复用以太坊开源合约库时选 EVM，需要复杂业务逻辑与 Java 生态时选 HVM。
