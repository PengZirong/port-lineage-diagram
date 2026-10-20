# 模型契约 · v1.0

这是本 Skill 的简洁输入格式，不是 OpenLineage、PROV、BPMN 或 UML 的导入导出协议。
JSON 中只保存直接依赖，根来源和高亮路径运行时计算。

## 最小完整模型

```json
{
  "schema_version": "1.0",
  "mode": "example",
  "title": "数量规范化",
  "nodes": [
    {
      "id": "input",
      "label": "输入",
      "kind": "source",
      "fields": [{
        "id": "qty", "label": "数量", "type": "str", "op": "root",
        "origin": {"kind": "input", "locator": "request.qty"},
        "sample": "2"
      }]
    },
    {
      "id": "output",
      "label": "规范输出",
      "kind": "output",
      "fields": [{
        "id": "quantity", "label": "数量", "type": "int", "op": "cast",
        "from": ["input.qty"], "rule": "parse_positive_integer(input.qty)",
        "sample": 2
      }]
    }
  ]
}
```

## 顶层

| 字段 | 含义 |
|---|---|
| `schema_version` | 固定 `"1.0"`。 |
| `mode` | `example` 构造示例；`design` 设计声明；`grounded` 基于真实材料。 |
| `title`、`nodes` | 标题与非空节点数组。 |
| `subtitle`、`scope`、`assumptions` | 可选简述、范围及边界说明。 |
| `outputs` | 可选完整字段引用列表；默认取 `kind=output` 的所有字段。 |
| `default_field` | 可选初始详情字段，不改变主图默认“全部血缘”模式。 |
| `routes`、`annotations`、`controls` | 可选的绕线、说明、显式控制边。 |

## 节点

必须有 `id`、`label`、`kind`、`fields`。

`kind` 取 `source / process / reference / config / output`；主要决定卡片配色，不替代字段来源定义。
`id` 用英文字母开头，只允许英文字母、数字、下划线和连字符；唯一。
`label` 是中文名称，`short` 是可选短称，`subtitle` 是可选副标题。

`position: [x,y]` 可固定左上角；一份图要么所有节点都有坐标，要么都没有。
`width` 为 240–900 像素，默认 300；高度从实际字段数计算。
坐标是显示信息，不改变字段依赖和流程顺序。

## 字段

必须有 `id`、`label`、`type`、`op`。
字段完整身份为 `node_id.field_id`。节点内字段 ID 唯一；不同节点同名字段不是同一个对象。

`type` 是显示用的类型声明，验证器仅检查透传 / 更名是否保持同样类型，不解析完整类型系统。
`int/分` 表示金额以整数分保存；查看器把数值样例附加显示为元。其他类型不做业务推断。

`sample` 是可选示例值；`note` 为额外解释；`display_rule` 是短规则，只控制展示。
`rule` 为完整规则文字，不会被执行。显示文字过长时详情保留完整值。

### 操作

| op | 约束 |
|---|---|
| `root` | 有 `origin`，无 `from`。 |
| `identity` | 恰好一条值依赖，保持字段值和类型。 |
| `rename` | 恰好一条值依赖，只改名字，类型不变。 |
| `cast`、`normalize` | 一条依赖，必须写规则。 |
| `derive`、`aggregate` | 一条或多条依赖，必须写规则。 |
| `lookup` | 记录查找键与取值来源，必须写查找与未匹配规则。 |
| `choose` | 至少两条带 `when` 的候选依赖，必须写分支选择规则。 |
| `unknown` | 有解释 `note`，无 `origin/from`；不能算作来源覆盖完成。 |

### 合法根来源

```json
"origin": {"kind": "config", "locator": "shipping.fees@version-2"}
```

`kind` 取 `input / database / api / file / config / constant / runtime`。
`locator` 为非空的来源说明：如表.列、接口响应字段、配置键、常量定义或时钟 API。
不要把未解释的新字段统一伪装成 `runtime`。
需要真实验证时 `locator` 要足够精确；读取它不会触发文件或网络访问。

### 依赖

简写字符串表示 `value` 值依赖：

```json
"from": ["clean.quantity", "clean.unit_price_fen"]
```

复杂关系：

```json
"from": [
  {"ref": "clean.coupon_code", "role": "selector"},
  {"ref": "coupons.amounts", "role": "value"}
]
```

`value` 提供输出值或计算用数值；`selector` 决定选中哪条数据；`condition` 决定记录 / 分支是否参与。
这里优惠码不是优惠金额的字符来源，但它影响选中哪一个金额，因此仍在可解释来源闭包中。
侧栏分别标记根来源承担的角色，不把所有根节点都解释成直接值来源。

依赖可加 `when` 描述静态分支条件。当前查看器显示所有可能来源，不解释为某次运行中全部执行。
`choose` 的条件互斥 / 穷尽性由制图者校验；脚本只检查条件文字存在，不做逻辑定理证明。

### 状态与证据

`status` 可选：`declared / verified / unknown`，默认 `declared`。
`verified` 要求顶层 `mode=grounded` 且该字段提供 `evidence`。
`evidence` 应写已查看的代码位置、文档定位或测试记录，不能捏造文件名和行号。

“来源覆盖”只要求所有分支最终到达合法根且无未知；“验证覆盖”还要求沿路字段全部标记验证且有证据。
验证器检查证据字段是否存在，不核实证据文件、行号或结论真假；仍需 Agent / 人工读源核验。

## 跨步骤传递、JOIN 与循环

从 `clean.order_id` 直接接到 `checkout.order_id` 表示真实旁路，而不是所有中间节点自动拥有它。
若真实代码经过某节点，必须把那一步的透传字段和关系记录出来。

单次调用在同一请求对象内汇合，不需要虚构 JOIN 键。
实际数据库 JOIN 需在规则中写清连接键、类型、基数、冲突和未匹配行为；键以 selector/condition 表达。

未版本化数据环会被拒绝。将迭代值拆为 `step_i0.value`、`step_i1.value` 等，状态反馈的版本关系仍存在。
控制回边可单独添加：

```json
"controls": [{"from":"checkout","to":"clean","label":"失败时重试；最多 2 次","loop":true}]
```

这只画控制语义，不执行重试。复杂回边可以提供数值坐标 `via` 供绕线。

## 绕线

```json
"routes": {
  "clean.order_id->checkout.order_id": [[735,610],[1230,610]]
}
```

坐标不得改变端点，不得删除依赖。自动布局会尝试把穿过第三个节点的长边绕到外围；不是最优图布局算法。
最后必须用浏览器检查实际路径。大型图优先缩小范围或做同图的渐进展开，而不是无限堆叠字段。
