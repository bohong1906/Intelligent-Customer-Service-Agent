## 05/16

這次改動：

1. main.py
   目前 workflow 如下。

   目前流程：

   ```text
   User Input
   -> Planner Node
   -> ReAct Agent Node
   -> Tool Node?
      yes -> Verifier Node -> ReAct Agent Node
      no  -> Verifier Node -> Long-Term Memory Write Node -> END
   ```

   說明：

   - ReAct Agent Node 同時負責工具選擇與最終客服回答。
   - Verifier Node 是單一 node，會依最後訊息型別驗證 tool output 或 final response。
   - LTM write 放在最後，避免 tool / response 修正 loop 重複寫入 memory。
   - `MAX_TOOL_ITERATIONS` 防止工具迴圈無限執行。
   - `MAX_RESPONSE_REVISIONS` 防止 final response 修正迴圈無限執行。

2. planner.py
   planner output 維持 structured result。
   目前會輸出：

   - intent
   - customer_id
   - order_id
   - product
   - date
   - entities
   - requires_tools
   - recommended_tools
   - plan
   - missing_info
   - safety_notes
   - ltm

   目前會使用 `.env` 裡的 `CURRENT_CUSTOMER_ID` 作為 demo 使用者。

3. tools.py
   目前有四個 MySQL-backed customer service tools：

   - OrderLookupTool
   - CustomerProfileTool
   - RefundTool
   - ComplaintLoggerTool

4. ltm.py
   新增 long-term memory helper。
   LTM 存在 MySQL `customer_memory` table。

   目前支援：

   - 依 `customer_id` 讀 memory
   - 依 `order_id` 找 customer 後讀 memory
   - 寫入 customer memory
   - 從 tool/message payload 裡推 customer_id
   - 從 `.env CURRENT_CUSTOMER_ID` 取得目前 demo customer

5. verifier.py
   Verifier 維持單一 node。

   - 最後訊息是 `ToolMessage` 時，驗證工具輸出。
   - 最後訊息是 `AIMessage` 時，驗證 final response。
   - final response 若回 `ISSUE:`，會回到 ReAct Agent Node 重新生成，最多 `MAX_RESPONSE_REVISIONS` 次。

6. README.md
   補上：

   - 最新 workflow
   - `.env` 格式
   - MySQL reset / rebuild 流程
   - local test commands
   - 11 個 demo query 的連續測試流程

確認目前 main.py 註冊的 tools：

```bash
conda run -n ics-agent python -c "import main; print([t.name for t in main.CUSTOMER_SERVICE_TOOLS])"
```

預期結果：

```text
['OrderLookupTool', 'CustomerProfileTool', 'RefundTool', 'ComplaintLoggerTool']
```


Demo 前建議重建 MySQL 資料：

```sql
SET FOREIGN_KEY_CHECKS=0;
DROP TABLE IF EXISTS customer_memory, complaints, orders, customers;
SET FOREIGN_KEY_CHECKS=1;
SOURCE /home/hislab/Intelligent-Customer-Service-Agent/schema.sql;
```


11 個 demo query：

```text
Where is my order 12345?
Check status of order 1001
Show my profile
Refund order 1001
I want to complain about order 2222 because the monitor delivery is taking too long
Refund order 2222 if delivered
Cancel it
What issues have I had before?
Remember I prefer refunds
My order is late again
Refund order 0000
```


目前仍需注意：

1. `schema.sql` 直接重跑可能遇到 duplicate index。
   Demo 前建議先 drop 四張 project tables 再 source schema。

2. Planner 目前只提供 structured guidance，例如 intent、entities、recommended_tools、plan。
   實際是否呼叫工具仍由 ReAct Agent Node 決定，因此 planner 規劃不會強制執行工具。
   這符合 ReAct 形式，但 demo 結果會受到 LLM tool-calling 判斷影響。

3. LTM 目前是 MySQL `customer_memory` key/value 紀錄。
   從 SQL client 看起來會比較像 user interaction log / customer memory log。
   這基本符合 spec 中 preferences、interaction history、issue patterns 的要求，但展示上不像完整 customer profile。

4. 個人化目前主要依賴 STM + LTM summary 進 prompt。
   若 `customer_memory` 內沒有足夠資料，demo 時個人化差異會不明顯。
   可以先跑 `Remember I prefer refunds`、`My order is late again` 後再測 `What issues have I had before?`。

5. `test.py` 目前是 local routing / helper tests，沒有完整覆蓋 PDF 內 11 個 demo query 的端到端 LLM 行為。
   完整 demo 仍需要人工在同一個 `python main.py` session 中連續輸入 11 個 query。

6. Graph ReAct Loop 次數目前有基本控制。
   `MAX_TOOL_ITERATIONS` 預設是 4，控制 tool calling loop。
   `MAX_RESPONSE_REVISIONS` 預設是 2，控制 final response 被 verifier 判定 `ISSUE:` 後回到 ReAct Agent Node 重新生成的次數。
   這兩個值可以在 `.env` 覆蓋。


後續可改進：

1. `Refund order 2222 if delivered` 的條件式退款，目前主要依賴 ReAct agent 推理。
   `RefundTool` 本身還沒有硬性檢查 delivered/shipped 狀態決定是否同意辦理退單。

2. `.env` 內雖然設置 customer id 來控制當前使用者角色，但目前工具層並未完整查核訂單是否屬於該顧客。
   後續可以在 OrderLookupTool / RefundTool / ComplaintLoggerTool 加入 customer ownership policy。

3. LTM 目前是 key/value log，後續可以加 memory summarization、去重、profile merge，讓個人化更明顯。
