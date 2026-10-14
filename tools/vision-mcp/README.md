# GLM 独立视觉 MCP

GLM研究模型继续使用config/glm.local.toml；图像工具读取config/glm-vision.local.toml。凭据按credential_profile引用服务端配置，不写入前端、命令行或证据。

本项目固定安装官方@z_ai/mcp-server 0.1.5与@modelcontextprotocol/sdk 1.26.0。安装/迁移：Node.js 22以上，在项目根运行npm ci --prefix tools/vision-mcp --ignore-scripts。共享依赖目录不写入。

当前平台ZHIPU，视觉模型glm-5.3-flash（官方MCP当前默认视觉模型）；国际Z.AI账号使用ZAI且须匹配其密钥。禁止用GLM文本模型作为视觉失败后的静默替代。

- read_source_image继续本地RapidOCR，失败时仍归档原图。
- read_source_table通过extract_text_from_screenshot做整页/放大图独立转录，原有坐标、表号、合并单元格与一致性校验保留。
- digitize_source_chart通过analyze_data_visualization读取像素结构，仍须线性坐标/实测标记校验，不创造曲线。
- GPT沿用现有视觉模型路径。

MCP返回值须通过Pydantic及既有科学校验。所有图像读数仍为image_estimate，并非人工或实验核验。官方MCP可能有独立套餐权限/额度；文字模型连通不代表视觉可用。视觉出错保留明确失败，不升级证据身份。

单次MCP限150秒，进程错误/取消清理子进程与临时图像，原件保留。供应商stderr不会写入用户日志。

官方说明：https://docs.z.ai/devpack/mcp/vision-mcp-server
