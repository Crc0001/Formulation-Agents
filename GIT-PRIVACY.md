# Git 内容边界

提交程序源码、测试、依赖清单以及 `.gitignore` 明确放行的公开参考示例和研究规则。
本机密钥配置、数据库、上传资料、运行对话、日志、备份、批次导出、工作记录、
私有研究档案及前端私人实验数据保持在本机，不随源码提交。

`reference` 默认忽略，新资源需要逐文件审查后加入白名单。
`apps/web/src/mecobalamin-pair-data.json` 是私人实测数据；缺失时页面显示未导入。
私人数据存在时仍可能被打进本机构建产物，因此 `dist` 同样不提交；不要直接公开本机部署包。
公开案例可随源码使用，用户实验校准等功能需要私下导入对应数据，不能用假数据补齐。
便携 Python、Node 依赖和可执行工具也不提交，新环境需自行安装运行依赖。

提交前检查：

```sh
git status --short
git diff --cached --name-only
git check-ignore -v config/glm.local.toml data/origin.sqlite3
```

`.gitignore` 不会清除已经提交的历史，也不能阻止 `git add -f`。不要强制添加以上私有目录。
