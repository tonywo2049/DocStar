# 规则就地绑 kind 的假绿证明语料（EG-20-AC3/AC5）

同一语义、两种写法的开放 kind。required_edges 只点名「需求」写法，
「Requirements」写法落在政策网外——确定性检查精确匹配 kind，故后者静默无检（假绿），
只有「未覆盖kind」告警把它显式化。

## 需求

- **需求甲** 甲的验收标准
- **需求乙** 乙的验收标准

## Requirements

- **ReqA** acceptance for A
- **ReqB** acceptance for B
