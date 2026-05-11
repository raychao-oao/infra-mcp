#!/bin/bash
# 檔案路徑：scripts/ai_helpers.sh
# 版本：v6.1
# 版本時間：2025-10-16

# AI 協作輔助函數 - v6.1 (Haiku 4.5 整合)
# 極簡化設計：task-type 驅動 + 自動日誌 + prompt 外部化

# 更新日誌：
# v6.1 (2025-10-16): Haiku 4.5 整合
#   - 新增 haiku-claude wrapper 支援
#   - implement/fix 任務改用 haiku（速度優勢）
#   - architect 保持 sonnet（深度思考）
# v6.0 (2025-10-15): 重大重構
#   - Task type 驅動工具選擇（research→gemini, implement→haiku, review→codex）
#   - 底層 wrapper 自動日誌記錄（透過 AI_LOG_FILE 環境變數）
#   - Prompt 模板外部化（scripts/prompts/*.txt）
#   - --follow 參數自動讀取前次輸出並傳遞上下文
#   - --tool 參數可覆寫預設工具（應對 API 額度限制）
#   - 流程函數簡化為階段序列執行
#   - 刪除 4 個獨立函數，整合到 ai_execute
#   - 程式碼從 1080 行減少到 ~280 行（-74%）

# ============================================
# 基礎設定
# ============================================

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 取得專案根目錄
get_project_root() {
    git rev-parse --show-toplevel 2>/dev/null || pwd
}

# 顯示狀態訊息
show_status() {
    local type=$1
    local message=$2
    case $type in
        "info")
            echo -e "${BLUE}ℹ${NC} $message"
            ;;
        "success")
            echo -e "${GREEN}✓${NC} $message"
            ;;
        "warning")
            echo -e "${YELLOW}⚠${NC} $message"
            ;;
        "error")
            echo -e "${RED}✗${NC} $message"
            ;;
        "progress")
            echo -e "${BLUE}▶${NC} $message"
            ;;
    esac
}

# 初始化目錄結構
init_directories() {
    local project_root=$(get_project_root)
    local date=$(date +%Y-%m-%d)
    mkdir -p "$project_root/docs/ai_collaboration/$date"/{plans,workflows,artifacts,reports}
    mkdir -p "$project_root/logs"
}

# 解析自訂工作流名稱
parse_workflow_name() {
    echo "${WORKFLOW_NAME:-}"
}

# ============================================
# Task Type 配置表
# ============================================

declare -A TASK_DEFAULTS

TASK_DEFAULTS[research]="gemini"
TASK_DEFAULTS[implement]="haiku"
TASK_DEFAULTS[review]="codex"
TASK_DEFAULTS[fix]="haiku"
TASK_DEFAULTS[diagnose]="gemini"
TASK_DEFAULTS[verify]="codex"
TASK_DEFAULTS[document]="gemini"
TASK_DEFAULTS[architect]="sonnet"
TASK_DEFAULTS[evaluate]="codex"
TASK_DEFAULTS[adr]="gemini"

# ============================================
# 日誌管理函數
# ============================================

# 尋找前一個階段的日誌檔案（支援跨日查詢，最多回溯 7 天）
# 因為不會並行作業，所以直接找最新的 log 即為前一階段的輸出
# 參數 $1: 當前的 log 路徑（用於排除自己）
find_latest_log() {
    local project_root=$(get_project_root)
    local current_log="${1:-}"
    local days_back=0

    while [ $days_back -le 7 ]; do
        local check_date=$(date -d "$days_back days ago" +%Y-%m-%d 2>/dev/null || date -v-${days_back}d +%Y-%m-%d)
        local log_dir="$project_root/docs/ai_collaboration/$check_date/workflows"

        if [ -d "$log_dir" ]; then
            # 尋找最新的 log（按檔名時間戳排序，因為不會並行作業）
            # 如果有 current_log，排除它；否則排除最新的（正在寫入的）
            local all_logs=$(ls -t "$log_dir"/*.log 2>/dev/null)

            for log in $all_logs; do
                # 跳過當前正在寫入的檔案
                if [ -n "$current_log" ] && [ "$log" = "$current_log" ]; then
                    continue
                fi
                # 找到第一個不是當前檔案的 log，就是前一階段的
                echo "$log"
                return 0
            done
        fi

        days_back=$((days_back + 1))
    done

    return 1
}

# 產生日誌檔案路徑
generate_log_path() {
    local project_root=$(get_project_root)
    local date=$(date +%Y-%m-%d)
    local time=$(date +%H%M%S)
    local tool=$1
    local task_type=$2

    # 自動建立目錄（支援獨立作業）
    local log_dir="$project_root/docs/ai_collaboration/$date/workflows"
    mkdir -p "$log_dir"

    echo "$log_dir/${time}_${tool}_${task_type}.log"
}

# 載入 prompt 模板
load_prompt_template() {
    local project_root=$(get_project_root)
    local task_type=$1
    local prompt_file="$project_root/scripts/prompts/${task_type}.txt"

    if [ ! -f "$prompt_file" ]; then
        show_status "error" "找不到 prompt 模板：$prompt_file"
        return 1
    fi

    # 讀取模板並替換變數
    local template=$(cat "$prompt_file")
    template="${template//\{\{PROJECT_ROOT\}\}/$project_root}"

    echo "$template"
}

# ============================================
# 核心執行函數
# ============================================

# ai_execute - task-type 驅動的 AI 執行函數
# 參數:
#   --task-type: 任務類型（research/implement/review/fix/diagnose/verify/document/architect/evaluate/adr）
#   --tool: 覆寫預設工具（gemini/sonnet/codex）
#   --follow: 讀取前次輸出作為上下文
#   --prompt: 額外的 prompt 內容
ai_execute() {
    local task_type=""
    local tool=""
    local follow=false
    local extra_prompt=""

    # 解析參數
    while [[ $# -gt 0 ]]; do
        case $1 in
            --task-type)
                task_type="$2"
                shift 2
                ;;
            --tool)
                tool="$2"
                shift 2
                ;;
            --follow)
                follow=true
                shift
                ;;
            --prompt)
                extra_prompt="$2"
                shift 2
                ;;
            *)
                show_status "error" "未知參數：$1"
                return 1
                ;;
        esac
    done

    # 驗證必要參數
    if [ -z "$task_type" ]; then
        show_status "error" "必須指定 --task-type"
        return 1
    fi

    # 選擇工具（優先使用 --tool，否則使用預設）
    if [ -z "$tool" ]; then
        tool="${TASK_DEFAULTS[$task_type]}"
        if [ -z "$tool" ]; then
            show_status "error" "未知的 task_type：$task_type"
            return 1
        fi
    fi

    show_status "info" "Task: $task_type | Tool: $tool"

    # 載入 prompt 模板
    local prompt=$(load_prompt_template "$task_type")
    if [ $? -ne 0 ]; then
        return 1
    fi

    # 如果有額外 prompt，附加上去
    if [ -n "$extra_prompt" ]; then
        prompt="$prompt

$extra_prompt"
    fi

    # 產生日誌路徑（必須先產生，才能傳給 find_latest_log 排除自己）
    local log_file=$(generate_log_path "$tool" "$task_type")

    # 如果需要 follow，讀取前次輸出
    local context=""
    if [ "$follow" = true ]; then
        local prev_log=$(find_latest_log "$log_file")
        if [ $? -eq 0 ]; then
            show_status "info" "讀取前次輸出：$prev_log"
            context="

--- 前次輸出 ---
$(cat "$prev_log")
--- 前次輸出結束 ---
"
            prompt="$prompt$context"
        else
            show_status "warning" "找不到前次輸出，繼續執行"
        fi
    fi

    export AI_LOG_FILE="$log_file"

    show_status "progress" "執行中... (日誌：$log_file)"

    # 根據工具執行
    case $tool in
        gemini)
            gemini-claude --approval-mode yolo -o text -p "$prompt"
            ;;
        sonnet)
            sonnet-claude --permission-mode acceptEdits -p "$prompt"
            ;;
        haiku)
            haiku-claude --permission-mode acceptEdits -p "$prompt"
            ;;
        codex)
            codex-claude exec "$prompt"
            ;;
        opus)
            opus-claude --permission-mode acceptEdits -p "$prompt"
            ;;
        *)
            show_status "error" "未知的工具：$tool"
            return 1
            ;;
    esac

    local exit_code=$?
    unset AI_LOG_FILE

    if [ $exit_code -eq 0 ]; then
        show_status "success" "完成 $task_type"
    else
        show_status "error" "$task_type 執行失敗"
    fi

    return $exit_code
}

# ============================================
# 流程執行函數
# ============================================

# ai_execute_flow - 執行多階段流程
# 參數:
#   --prompt: 任務描述（會傳給第一個階段）
#   其餘參數: 階段列表，每個階段格式為 "task_type[:tool]"
# 範例: ai_execute_flow --prompt "更新官網內容" "research" "implement:sonnet" "review"
ai_execute_flow() {
    local prompt=""
    local stages=()

    # 解析參數
    while [[ $# -gt 0 ]]; do
        case $1 in
            --prompt)
                prompt="$2"
                shift 2
                ;;
            *)
                stages+=("$1")
                shift
                ;;
        esac
    done

    if [ ${#stages[@]} -eq 0 ]; then
        show_status "error" "必須指定至少一個階段"
        return 1
    fi

    show_status "info" "開始執行流程，共 ${#stages[@]} 個階段"

    local stage_num=1
    for stage in "${stages[@]}"; do
        show_status "progress" "階段 $stage_num/${#stages[@]}: $stage"

        # 解析階段（格式：task_type 或 task_type:tool）
        local task_type="${stage%%:*}"
        local tool="${stage#*:}"

        # 如果沒有指定 tool，清空變數
        if [ "$tool" = "$task_type" ]; then
            tool=""
        fi

        # 執行階段（第一階段不 follow，後續階段都 follow）
        if [ $stage_num -eq 1 ]; then
            # 第一階段：可以加上 --prompt
            if [ -n "$prompt" ]; then
                if [ -n "$tool" ]; then
                    ai_execute --task-type "$task_type" --tool "$tool" --prompt "$prompt"
                else
                    ai_execute --task-type "$task_type" --prompt "$prompt"
                fi
            else
                if [ -n "$tool" ]; then
                    ai_execute --task-type "$task_type" --tool "$tool"
                else
                    ai_execute --task-type "$task_type"
                fi
            fi
        else
            # 後續階段：使用 --follow
            if [ -n "$tool" ]; then
                ai_execute --task-type "$task_type" --tool "$tool" --follow
            else
                ai_execute --task-type "$task_type" --follow
            fi
        fi

        if [ $? -ne 0 ]; then
            show_status "error" "階段 $stage_num 失敗，中止流程"
            return 1
        fi

        stage_num=$((stage_num + 1))
    done

    show_status "success" "流程完成"
    return 0
}

# ============================================
# 預設工作流
# ============================================

# 功能開發流程：研究 → 實作 → 審查 → 文件
ai_workflow_feature() {
    local description="$1"

    show_status "info" "功能開發流程：$description"

    ai_execute_flow \
        --prompt "$description" \
        "research" \
        "implement" \
        "review" \
        "document"
}

# Bug 修復流程：診斷 → 修復 → 驗證 → 文件
ai_workflow_bugfix() {
    local description="$1"

    show_status "info" "Bug 修復流程：$description"

    ai_execute_flow \
        --prompt "$description" \
        "diagnose" \
        "fix" \
        "verify" \
        "document"
}

# 架構決策流程：研究 → 評估 → 設計 → ADR
ai_workflow_architecture() {
    local description="$1"

    show_status "info" "架構決策流程：$description"

    ai_execute_flow \
        --prompt "$description" \
        "research" \
        "evaluate" \
        "architect" \
        "adr"
}

# ============================================
# 主入口函數
# ============================================

# claude_execute - 主入口函數（保持向後相容）
claude_execute() {
    local workflow_type=$1
    shift
    local description="$*"

    # 初始化目錄
    init_directories

    # 根據 workflow 類型執行
    case $workflow_type in
        feature)
            ai_workflow_feature "$description"
            ;;
        bugfix)
            ai_workflow_bugfix "$description"
            ;;
        architecture)
            ai_workflow_architecture "$description"
            ;;
        *)
            show_status "error" "未知的 workflow 類型：$workflow_type"
            show_status "info" "可用類型：feature, bugfix, architecture"
            return 1
            ;;
    esac
}

# ============================================
# 初始化訊息
# ============================================

show_status "success" "AI 協作輔助函數 v6.1 已載入"
show_status "info" "可用指令："
echo "  - claude_execute feature \"描述\"     # 功能開發流程"
echo "  - claude_execute bugfix \"描述\"      # Bug 修復流程"
echo "  - claude_execute architecture \"描述\" # 架構決策流程"
echo "  - ai_execute --task-type TYPE        # 單一任務執行"
echo "  - ai_execute_flow \"stage1\" \"stage2\" # 自訂流程"

