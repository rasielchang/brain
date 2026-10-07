# Brain

**給同時管理多個專案的人使用的 AI 工作管理框架。**

把任務承諾、工程證據和 Markdown 工作記憶放在一起，回答：**現在什麼事需要我？為什麼？**

[English](README.md) · [架構](docs/architecture.md) · [設定](docs/configuration.md)

## 一分鐘試跑

需要 Python 3.10 以上、macOS 或 Linux。下載這個 repo 後：

```bash
git clone https://github.com/rasielchang/brain.git
cd brain
python3 bin/brain.py demo
```

不需要 API token 或 AI 帳號，不連網、不呼叫模型。使用虛構資料，在 `.brain/demo/` 產生日報、週報、風險與專案總覽。[示範日報](examples/today.md)

## 五個工作流程

| Codex | Claude Code | 用途 |
|---|---|---|
| `$today` | `/today` | 今日本人待辦、等待狀態、重點專案與固定工作 |
| `$weekly` | `/weekly` | 跨專案週會準備與待決事項 |
| `$radar` | `/radar` | 對照承諾與工程證據，找交付風險 |
| `$schedule` | `/schedule` | 依工量、前置與共用容量提議時程 |
| `$inbox` | `/inbox` | 整理貼入的訊息、文件，產生可追溯紀錄與更新草稿 |

在 repo 內開啟 Codex 或 Claude Code，就能使用對應流程。

## 開始使用自己的資料

```bash
python3 bin/brain.py init
# 參考 examples/config.json，編輯 .brain/config.json
python3 bin/brain.py doctor
python3 bin/brain.py refresh
python3 bin/brain.py brief
```

第一次初始化沒有任何已連線專案。自行設定 Asana／GitLab 對應、角色、每週重點、固定工作與休假；`language` 可填 `zh-TW` 供 AI 報告使用。目前不呼叫 AI 的來源摘要固定使用英文。

憑證可來自環境變數、macOS Keychain 或密碼管理工具命令；不要把 token 寫進 JSON 或 repo。詳見[設定方式](docs/configuration.md)。

`refresh` 更新專案總覽與原始快照。`brief` 產生 `daily/日期.source.md`，保存可核對的來源資料；互動後的判斷與決議另放 `daily/日期.md`，不會被普通刷新覆蓋。

需要 AI 整理時，先安裝並登入對應 CLI：

```bash
python3 bin/brain.py brief --agent codex
# 或 --agent claude
```

此操作會將快照內容傳給選定的 AI 服務，可能消耗方案額度。自動報告只分析已提供資料；需要即時查核或決策時，使用互動 Skills。API 抓取失敗會保留舊快照；AI 報告失敗會保留原報告。

## 資料與權限

- Asana 保存任務與承諾，GitLab 提供工程證據；Brain 保存本機判斷、提醒與來源。
- `.brain/`、日報、週報、專案記憶與收件匣預設不進 Git。
- 內建 Python API 整合只有讀取功能。外部任務更新需要使用者授權和另外可用的寫入工具；沒有工具時會留下草稿，不能冒稱已同步。
- 專案對話只在使用者指定路徑後，由互動 agent 查閱；不會自動掃整台電腦。
- 到期日不直接等於今天急件；MR 合併、正式部署、交測、驗收分別追蹤。

## 每日自動執行

`python3 bin/brain.py morning` 刷新並產生來源摘要，週一多產週報與風險摘要。加上 `--agent` 才會呼叫 AI。

`python3 bin/brain.py launchd` 只產生 macOS 排程檔供檢查，不直接安裝。macOS／Linux 的設定與停止方式見[排程文件](docs/automation.md)。

目前 v0.1 包含五個 Skills、Asana／GitLab 唯讀整合、離線示範與排程工具。LINE webhook、Web 介面、GitHub 資料整合、自動寫任務與自動解析對話紀錄尚未實作。

MIT 授權。歡迎分享工作流程與改進；提交時請使用虛構資料。
