## 05/13

這次改動：


1. main.py
   從原本 planner-only workflow 改成 Planner + ReAct Agent + ToolNode。
   目前流程：
   User Input -> Planner Node -> ReAct Agent Node -> ToolNode -> ReAct Agent Node -> Final Response

2. planner.py
   planner output 改成比較完整的 structured result。
   會輸出 intent、entities、requires_tools、recommended_tools、plan、missing_info、safety_notes。

3. tools.py
   新增 MySQL-backed customer service tools。
   目前有：
   OrderLookupTool
   CustomerProfileTool
   RefundTool
   ComplaintLoggerTool

4. requirements.txt
   補上目前專案需要的 langchain / langgraph / mysql connector 等套件版本。

5. README.md
   補上目前怎麼跑 Planner + ReAct Agent。


測試：

```bash
conda activate ics-agent
python main.py
```


確認目前 main.py 註冊的 tools：

```bash
conda run -n ics-agent python -c "import main; print([t.name for t in main.CUSTOMER_SERVICE_TOOLS])"
```

預期結果：

```text
['OrderLookupTool', 'CustomerProfileTool', 'RefundTool', 'ComplaintLoggerTool']
```



預計最後比較完整的 workflow：

```text
User Input
-> Memory Read Node
-> Planner Node
-> ReAct Agent Node
-> ToolNode
-> ReAct Agent Node
-> Memory Update Node
-> Verifier Node
-> Final Response
```
