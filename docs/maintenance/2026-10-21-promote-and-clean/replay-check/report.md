# 首轮保存页回放

范围：5份既有个人页原件、1份有60条参考身份的名单原件，以及本地HTTP失败注入。
正文指标只检查既有DOM范围内长度≥8的文本节点是否完整出现在输出；不等于全文完整性、字段正确性或跨站泛化。
Crawl4AI 此处测试 CSS 提取与 HTML→Markdown 模块；未测试浏览器、自动规则生成或模型提取。

| 样本 | 方法 | 保留参考文本节点 | 输出字符 | 秒 |
|---|---|---:|---:|---:|
| nxmu-0 | trafilatura-default | 111/111 | 3418 | 0.0199 |
| nxmu-0 | trafilatura-recall | 111/111 | 3418 | 0.0323 |
| nxmu-0 | crawl4ai-markdown | 111/111 | 8182 | 0.0135 |
| nxmu-1 | trafilatura-default | 55/55 | 1998 | 0.0153 |
| nxmu-1 | trafilatura-recall | 55/55 | 1998 | 0.01 |
| nxmu-1 | crawl4ai-markdown | 55/55 | 5516 | 0.0095 |
| cuc-1 | trafilatura-default | 124/124 | 4986 | 0.0348 |
| cuc-1 | trafilatura-recall | 124/124 | 4986 | 0.0278 |
| cuc-1 | crawl4ai-markdown | 124/124 | 9671 | 0.0145 |
| cuc-2 | trafilatura-default | 44/44 | 1307 | 0.0229 |
| cuc-2 | trafilatura-recall | 44/44 | 1307 | 0.0148 |
| cuc-2 | crawl4ai-markdown | 44/44 | 5380 | 0.0064 |
| stbu-1 | trafilatura-default | 5/5 | 433 | 0.0148 |
| stbu-1 | trafilatura-recall | 5/5 | 433 | 0.0131 |
| stbu-1 | crawl4ai-markdown | 5/5 | 5311 | 0.0064 |

名单：60条；参考差集漏项0，多项0。选择器由既有样本提供。
队列：成功2个唯一URL，耗尽重试后失败1个。请求次数：{'/ok': 1, '/retry-once': 2, '/always-fails': 2}

全院完整性未验证。原文、提取输出、逐项缺失和版本均保存在同一运行目录。