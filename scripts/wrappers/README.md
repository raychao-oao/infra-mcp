# AI CLI Wrappers (v6.0)

這些 wrapper 加入了自動日誌記錄功能。

## 安裝方式

```bash
sudo cp gemini-claude /usr/local/bin/
sudo cp sonnet-claude /usr/local/bin/
sudo cp codex-claude /usr/local/bin/
sudo chmod +x /usr/local/bin/gemini-claude
sudo chmod +x /usr/local/bin/sonnet-claude
sudo chmod +x /usr/local/bin/codex-claude
```

## 功能說明

當設定 `AI_LOG_FILE` 環境變數時，輸出會自動 tee 到該檔案：

```bash
AI_LOG_FILE="/path/to/log" gemini-claude -p "query"
```

ai_helpers.sh v6.0 會自動設定此環境變數。
